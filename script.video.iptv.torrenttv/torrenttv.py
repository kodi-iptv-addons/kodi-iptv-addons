# coding=utf-8
#
#      Copyright (C) 2018 Dmitry Vinogradov
#      https://github.com/kodi-iptv-addons
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
import json
import uuid
from urllib import quote

from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Torrenttv(Api):

    adult = None  # type: bool
    _guid = None  # type: str

    def __init__(self, adult, **kwargs):
        super(Torrenttv, self).__init__(**kwargs)
        self.adult = adult
        self.auth_status = self.AUTH_STATUS_NONE
        self._guid = addon.getSetting('guid')
        if self._guid == '':
            self._guid = str(uuid.uuid1()).replace('-', '')
            addon.setSetting('guid', self._guid)
        Model.API = self

    @property
    def base_api_url(self):
        return "http://%s/v3/%%s" % self.host

    @property
    def base_icon_url(self):
        return "http://torrent-tv.ru/uploads/%s"

    @property
    def host(self):
        return "1ttvxbmc.top"

    @property
    def diff_live_archive(self):
        return TENSECS

    @property
    def archive_ttl(self):
        return TREEDAYS

    def get_cookie(self):
        return ""

    def is_login_request(self, uri, payload=None, method=None, headers=None):
        return uri == "auth.php"

    def login(self):
        payload = {
            "username": self.username,
            "password": self.password,
            "typeresult": "json",
            "application": "xbmc",
            "guid": self._guid
        }
        response = self.make_request("auth.php", payload)
        if "error" in response and response["error"] != "":
            raise ApiException(response["error"], Api.E_AUTH_ERROR)

        self.auth_status = self.AUTH_STATUS_OK
        self.write_cookie_file("%s" % response["session"])

    def auth_payload(self, data=None):
        # type: (dict) -> dict
        cookie = self.read_cookie_file()
        if cookie == "" or self.auth_status != self.AUTH_STATUS_OK:
            self.login()
            return self.auth_payload(data)
        payload = data or {}
        payload["session"] = cookie
        payload["typeresult"] = "json"
        return payload

    def get_groups(self):
        payload = self.auth_payload({"type": "channel",})
        response = self.make_request("translation_list.php", payload)
        if "error" in response and response["error"]:
            raise ApiException(response["error"], Api.E_UNKNOW_ERROR)

        groups = OrderedDict()
        channels = OrderedDict()
        for group_data in response.get("categories", []):
            if all(k in group_data for k in ("id", "name", "adult")) is False:
                continue
            gid = str(group_data["id"])
            groups[gid] = Group(gid, group_data["name"], OrderedDict(), group_data["position"])

        for channel_data in response.get("channels", []):
            gid = str(channel_data["group"])
            if groups.has_key(gid) is False:
                continue
            group = groups[gid]

            if self.adult is False and bool(channel_data["adult"]):
                continue

            if bool(channel_data.get("access_user_http_stream", 0)) is False:
                continue

            cid = str(channel_data["id"])
            channel = Channel(
                cid=cid,
                gid=group.gid,
                name=channel_data["name"],
                icon=self.base_icon_url % channel_data["logo"],
                epg=channel_data["epg_id"] > 0,
                archive=bool(channel_data.get("access_user_archive_http", 0)),
                protected=bool(channel_data["adult"])
            )
            channel.data.update({"epg_id": channel_data["epg_id"]})
            group.channels[cid] = channels[cid] = channel
        return groups

    def get_stream_url(self, cid, ut_start=None):
        payload = self.auth_payload({"zone_id": "1", "nohls": "0", "channel_id": cid})
        response = self.make_request("translation_http.php", payload)
        if "error" in response and response["error"]:
            raise ApiException(response["error"], Api.E_UNKNOW_ERROR)
        url = response["source"]
        if ut_start is not None:
            url = "%s%sutc=%s&lutc=%s" % (url, "&" if "?" in url else "?", ut_start, int(time_now()))
        return url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        channel = self.channels[cid]
        if channel.epg is False or channel.epg_id == 0:
            return OrderedDict()

        requests = []
        days = (self.archive_ttl / DAY)
        start = int(time_now() - self.archive_ttl)
        for i in range(days):
            day = format_date(start + (i * DAY), custom_format="%d-%m-%Y")
            payload = self.auth_payload({"epg_id": channel.epg_id, "date": day})
            request = self.prepare_request("arc_records.php", payload)
            requests.append(request)

        requests.append(self.prepare_request("translation_epg.php", self.auth_payload({"epg_id": channel.epg_id})))

        results = self.send_parallel_requests(requests)

        epg = dict()
        prev_ts = None
        for key in sorted(results.iterkeys()):
            response = results[key]
            if "success" in response and response["success"] == 1:
                data = response["records"] if "records" in response else response["data"] if "data" in response else []
                for entry in data:
                    time = int(entry["time"]) if "time" in entry else int(entry["btime"]) if "btime" in entry else 0
                    time_to = int(entry["etime"]) if "etime" in entry else 0
                    epg[time] = dict({
                        "time": time,
                        "time_to": time_to,
                        "duration": 0,
                        "name": entry["name"]
                    })
                    if prev_ts is not None and epg[prev_ts]["time_to"] == 0:
                        epg[prev_ts]["time_to"] = time
                    prev_ts = time
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
                "",
                self.channels[cid].archive
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
