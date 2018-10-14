# coding=utf-8
#
#      Copyright (C) 2018 Dmitry Vinogradov
#      https://github.com/dmitry-vinogradov/kodi-iptv-addons
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA  02110-1301, USA.
#
from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Kartina(Api):
    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    adult = None  # type: bool
    _open_epg_cids = None  # type: list[str]

    def __init__(self, hostname, adult, **kwargs):
        super(Kartina, self).__init__(**kwargs)
        self.hostname = hostname
        self.adult = adult
        Model.API = self

    @property
    def base_api_url(self):
        return "http://%s/api/json/%%s" % self.host

    @property
    def base_icon_url(self):
        return "http://anysta.kartina.tv/assets/img/logo/comigo/1/%s.7.png"

    @property
    def host(self):
        return self.hostname

    @property
    def diff_live_archive(self):
        return HALFHOUR

    @property
    def archive_ttl(self):
        return TREEDAYS

    def get_cookie(self):
        return self.read_cookie_file()

    def is_login_uri(self, uri):
        return "login" in uri

    def login(self):
        payload = {
            "login": self.username,
            "pass": self.password,
            "softid": "xbmc",
            "settings": "all"
        }
        response = self.make_request("login", payload=payload, method="POST")

        self.auth_status = self.AUTH_STATUS_OK
        self.write_cookie_file("%s=%s" % (response["sid_name"], response["sid"]))
        self.write_settings_file(response)

        return response

    def get_groups(self):
        response = self.make_request("channel_list", method="POST")
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])

        groups = OrderedDict()
        for group_data in response["groups"]:
            if all(k in group_data for k in ("id", "name", "channels")) is False:
                continue
            channels = OrderedDict()
            for channel_data in group_data["channels"]:
                if bool(channel_data.get("is_video", 1)) is False:
                    continue
                group_data["id"] = str(group_data["id"])
                if self.adult is False and bool(channel_data.get("protected", False)) is True:
                    continue
                channel = Channel(
                    cid=str(channel_data["id"]),
                    gid=group_data["id"],
                    name=channel_data["name"],
                    icon=self.base_icon_url % channel_data["id"],
                    epg=True if int(channel_data.get("epg_start", 0)) > 0 else False,
                    archive=bool(channel_data.get("have_archive", 0)),
                    protected=bool(channel_data.get("protected", False))
                )
                channels[channel.cid] = channel
            groups[group_data["id"]] = Group(group_data["id"], group_data["name"], channels)
        return groups

    def get_stream_url(self, cid, ut_start=None):
        payload = {"cid": cid}
        if ut_start:
            payload["gmt"] = int(ut_start)
        response = self.make_request("get_url", payload)
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])
        url = response["url"]
        return url.replace("http/ts", "http").split()[0]

    def get_real_epg(self, cid):
        requests = []
        days = (self.archive_ttl / DAY) + 2
        while days % 4: days += 1
        start = int(time_now() - self.archive_ttl)
        for i in range(days):
            day = format_date(start + (i * DAY), custom_format="%d%m%y")
            request = self.prepare_request("epg", payload={"cid": cid, "day": day})
            requests.append(request)

        results = self.send_parallel_requests(requests, 0.40, 4)

        epg = dict()
        prev_ts = None
        for key in sorted(results.iterkeys()):
            response = results[key]
            if "error" not in response:
                for entry in response["epg"]:
                    title, descr = (entry["progname"] + "\n").split("\n", 1)
                    ts = int(entry["ut_start"])
                    epg[ts] = dict({
                        "time": ts,
                        "time_to": 0,
                        "duration": 0,
                        "name": title,
                        "descr": descr
                    })
                    if prev_ts is not None:
                        epg[prev_ts]["time_to"] = ts
                    prev_ts = ts
            else:
                log("error: %s" % response, xbmc.LOGDEBUG)

        programs = OrderedDict()
        prev = None  # type: Program
        for key in sorted(epg.iterkeys()):
            val = epg[key]
            program = Program(
                cid,
                self.channels[cid].gid,
                val["time"],
                val["time_to"],
                val["name"],
                val["descr"],
                self.channels[cid].archive
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs

    def get_epg(self, cid):
        if self._open_epg_cids is None:
            try:
                url = "https://iptv.kartina.tv/api/json/open_epg?get=channels"
                request = self.prepare_request(url)
                response = self.send_parallel_requests([request])[url]
                if "error" not in response:
                    self._open_epg_cids = []
                    for entry in response["channels"]:
                        self._open_epg_cids.append(entry["id"])
                else:
                    self._open_epg_cids = []
            except:
                self._open_epg_cids = []

        if cid not in self._open_epg_cids:
            return self.get_real_epg(cid)

        requests = []
        days = (self.archive_ttl / DAY) + 2
        while days % 4: days += 1
        start = int(time_now() - self.archive_ttl)
        for i in range(days):
            day = format_date(start + (i * DAY), custom_format="%d%m%y")
            request = self.prepare_request(
                "https://iptv.kartina.tv/api/json/open_epg",
                payload={"period": "day", "cid": cid, "dt": day}
            )
            requests.append(request)

        results = self.send_parallel_requests(requests, 0.20, 4)

        epg = dict()
        prev_ts = None
        for key in sorted(results.iterkeys()):
            response = results[key]
            if "error" not in response:
                for entry in response["report"][0]["list"]:
                    title, descr = (entry["progname"] + "\n").split("\n", 1)
                    ts = int(entry["ts"])
                    epg[ts] = dict({
                        "time": ts,
                        "time_to": 0,
                        "duration": 0,
                        "name": title,
                        "descr": descr
                    })
                    if prev_ts is not None:
                        epg[prev_ts]["time_to"] = ts
                    prev_ts = ts
            else:
                log("error: %s" % response, xbmc.LOGDEBUG)

        programs = OrderedDict()
        prev = None  # type: Program
        for key in sorted(epg.iterkeys()):
            val = epg[key]
            program = Program(
                cid,
                self.channels[cid].gid,
                val["time"],
                val["time_to"],
                val["name"],
                val["descr"],
                self.channels[cid].archive
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
