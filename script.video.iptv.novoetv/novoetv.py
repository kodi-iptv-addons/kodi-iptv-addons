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
from HTMLParser import HTMLParser

from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Novoetv(Api):
    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    adult = None  # type: bool
    _open_epg_cids = None  # type: list[str]

    def __init__(self, hostname, adult, **kwargs):
        super(Novoetv, self).__init__(**kwargs)
        self.hostname = hostname
        self.adult = adult
        Model.API = self

    @property
    def base_api_url(self):
        return "http://%s/api/json2/%%s" % self.host

    @property
    def base_icon_url(self):
        return "http://%s/_logos/channelLogos/%%s" % self.host

    @property
    def host(self):
        return self.hostname

    @property
    def diff_live_archive(self):
        return TENSECS

    @property
    def archive_ttl(self):
        return TREEDAYS

    def get_cookie(self):
        return ""

    def is_login_uri(self, uri, payload=None):
        return "login" in uri

    def login(self):
        payload = {
            "login": self.username,
            "pass": self.password,
            "settings": "all"
        }
        response = self.make_request("login.php", payload=payload, method="GET")
        if "error" in response:
            raise ApiException(
                response["error"].get("message", get_string(TEXT_AUTHENTICATION_FAILED_ID)),
                response["error"].get("code", Api.E_AUTH_ERROR)
            )

        self.auth_status = self.AUTH_STATUS_OK
        self.write_cookie_file("%s=%s" % (response["sid_name"], response["sid"]))
        self.write_settings_file(response)

        return response

    def auth_payload(self, data=None):
        # type: (dict) -> dict
        cookie = self.read_cookie_file()
        if cookie == "" or self.auth_status != self.AUTH_STATUS_OK:
            self.login()
            return self.auth_payload(data)
        payload = data or {}
        tmp = cookie.split("=")
        payload[tmp[0]] = tmp[1]
        return payload

    def get_groups(self):
        response = self.make_request("channel_list.php", payload=self.auth_payload(), method="GET")
        if self._last_error:
            raise ApiException(
                self._last_error.get("message", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                self._last_error.get("code", Api.E_UNKNOW_ERROR)
            )

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
                    icon=self.base_icon_url % channel_data["logo_big"],
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
        response = self.make_request("get_url.php", self.auth_payload(payload))
        if self._last_error:
            raise ApiException(
                self._last_error.get("message", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                self._last_error.get("code", Api.E_UNKNOW_ERROR)
            )
        url = response["url"]
        return url.replace("http/ts", "http").split()[0]

    def get_epg(self, cid):
        requests = []
        days = (self.archive_ttl / DAY) + 2
        while days % 4: days += 1
        start = int(time_now() - self.archive_ttl)
        for i in range(days):
            day = format_date(start + (i * DAY), custom_format="%d%m%y")
            request = self.prepare_request("epg.php", self.auth_payload({"cid": cid, "day": day}))
            requests.append(request)

        results = self.send_parallel_requests(requests, 0.40, 4)

        epg = dict()
        prev_ts = None
        for key in sorted(results.iterkeys()):
            response = results[key]
            if "error" not in response:
                for entry in response["epg"]:
                    title, descr = (HTMLParser().unescape(entry["progname"]) + "\n").split("\n", 1)
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
