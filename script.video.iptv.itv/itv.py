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
from urllib import quote

from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Itv(Api):
    PROTECTED_GROUP = u"Взрослый"
    TEXT_ERROR_WRONG_KEY_ID = 30005  # type: int

    key = None  # type: str
    adult = None  # type: bool
    hostname = None  # type: str
    _player_info = None  # type: list

    def __init__(self, hostname, key, adult, **kwargs):
        # type: (str, str, bool, dict) -> None
        super(Itv, self).__init__(**kwargs)
        self.hostname = hostname
        self.key = self.username = key
        self.adult = adult
        self.auth_status = self.AUTH_STATUS_NONE
        Model.API = self

    @property
    def base_api_url(self):
        return "http://%s/%%s" % self.hostname

    @property
    def base_icon_url(self):
        return "http://%s/icon/%%s" % self.hostname

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

    def is_login_request(self, uri, payload=None, method=None, headers=None):
        return uri == "" and payload.get("action") == "playerInfo"

    def login(self):
        self._player_info = []
        response = self.make_request("", {"action": "playerInfo", "ukey": self.key})
        if isinstance(response, list) and len(response) and response[0].get("response") == "No Token":
            raise ApiException(
                addon.getLocalizedString(self.TEXT_ERROR_WRONG_KEY_ID),
                Api.E_AUTH_ERROR
            )
        elif "error" in response and isinstance(response, dict):
            raise ApiException(
                response["error"].get("message", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                response["error"].get("code", Api.E_UNKNOW_ERROR)
            )

        self._player_info = response
        self.auth_status = self.AUTH_STATUS_OK
        return response

    def get_groups(self):
        if self._player_info is None:
            self.login()
        number = 1
        groups = OrderedDict()
        channels = OrderedDict()
        for channel_data in self._player_info:
            if groups.has_key(channel_data["cat_id"]) is False:
                gid = str(channel_data["cat_id"])
                groups[gid] = Group(
                    gid=gid,
                    name=channel_data["cat_name"],
                    channels=OrderedDict(),
                    number=number
                )
                number += 1
            group = groups[channel_data["cat_id"]]

            if self.adult is False and group.name == self.PROTECTED_GROUP:
                continue

            cid = str(channel_data["ch_id"])
            channel = Channel(
                cid=cid,
                gid=group.gid,
                name=channel_data["channel_name"],
                icon=self.base_icon_url % channel_data["logo"],
                epg=True,
                archive=bool(channel_data.get("rec", 0)),
                protected=group.name == self.PROTECTED_GROUP
            )
            channel.data.update({"server": channel_data["server"], "token": channel_data["token"]})
            group.channels[cid] = channels[cid] = channel
        return groups

    def get_stream_url(self, cid, ut_start=None):
        channel = self.channels[cid]
        url = "http://%s:25000/%s/" % (channel.data["server"], cid)
        if ut_start is None:
            return "%smono.m3u8?token=%s" % (url, channel.data["token"])
        return "%sindex-%s-%s.m3u8?token=%s" % \
               (url, int(ut_start), int(time_now() - ut_start), channel.data["token"])

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        channel = self.channels[cid]
        obj = quote(json.dumps({
                "action": "epg",
                "chid": cid,
                "name": channel.name,
                "token": channel.data["token"],
                "serv": channel.data["server"],
            }))

        response = self.make_request("epg.php?obj=%s" % obj)  # type: dict[str, list[dict]]
        if self._last_error:
            raise ApiException(
                self._last_error.get("message", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                self._last_error.get("code", Api.E_UNKNOW_ERROR)
            )

        programs = OrderedDict()
        prev = None
        for v in response["res"]:
            program = Program(
                cid,
                self.channels[cid].gid,
                int(v["startTime"]),
                int(v["stopTime"]),
                v["title"],
                v["desc"],
                self.channels[cid].archive
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
