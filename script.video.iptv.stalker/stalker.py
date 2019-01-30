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

from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Stalker(Api):
    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    adult = None  # type: bool
    timeshift = None  # type: int
    _open_epg_cids = None  # type: list[str]

    def __init__(self, hostname, timeshift, adult, **kwargs):
        super(Stalker, self).__init__(**kwargs)
        self.hostname = hostname
        self.timeshift = timeshift
        self.adult = adult
        Model.API = self

    @property
    def base_api_url(self):
        return "http://%s/stalker_portal/%%s" % self.host

    @property
    def base_icon_url(self):
        return "%s"

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

    def default_headers(self, headers=None):
        headers = headers or {}
        cookie = self.read_cookie_file()
        if cookie == "":
            self.login()
            return self.default_headers(headers)
        elif self.auth_status == Api.AUTH_STATUS_NONE:
            self.auth_status = Api.AUTH_STATUS_OK
        headers["Authorization"] = cookie
        headers["Accept"] = "application/json"
        headers["Accept-Language"] = "ru-RU"
        return headers

    def get_token_type(self, response):
        token_type = response.get("token_type", "Bearer")
        return token_type[0].upper() + token_type[1:]

    def is_login_request(self, uri, payload=None, method=None, headers=None):
        return "auth/token.php" in uri

    def login(self):
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password
        }
        response = self.make_request("auth/token.php", payload, method="POST")
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        if "error" in response:
            raise ApiException(
                response.get("error_description", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                Api.E_API_ERROR
            )

        self.auth_status = self.AUTH_STATUS_OK
        token_type = self.get_token_type(response)
        self.write_cookie_file("%s %s" % (token_type, response.get("access_token", "Unknown")))
        self.write_settings_file(response)

        return response

    def get_groups(self):
        settings = self.read_settings_file()
        if not settings:
            self.login()
            return self.get_groups()
        uri = "api/api_v2.php?_resource=users/%s/tv-genres" % settings.get("user_id")
        response = self.make_request(uri, headers=self.default_headers())
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        if "error" in response:
            raise ApiException(
                response.get("error_description", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                Api.E_API_ERROR
            )

        groups = OrderedDict()
        for group_data in response.get("results"):
            if all(k in group_data for k in ("id", "title", "censored", "number")) is False:
                continue
            groups[str(group_data["id"])] = Group(
                str(group_data["id"]),
                group_data["title"],
                OrderedDict(),
                int(group_data["number"])
            )

        channels = self.get_channels()
        for channel_data in channels:
            if self.adult is False and bool(channel_data.get("censored", False)) is True:
                continue
            channel = Channel(
                cid=str(channel_data["id"]),
                gid=str(channel_data["genre_id"]),
                name=channel_data["name"],
                icon=self.base_icon_url % channel_data["logo"],
                epg=True,
                archive=bool(channel_data.get("archive", 0)),
                protected=bool(channel_data.get("censored", False)),
                url=channel_data["url"]
            )
            groups[channel.gid].channels[channel.cid] = channel
        return groups

    def get_channels(self):
        # type: () -> list
        settings = self.read_settings_file()
        if not settings:
            self.login()
            return self.get_channels()
        uri = "api/api_v2.php?_resource=users/%s/tv-channels" % settings.get("user_id")
        response = self.make_request(uri, headers=self.default_headers())
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        if "error" in response:
            raise ApiException(
                response.get("error_description", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                Api.E_API_ERROR
            )
        return response.get("results")

    def get_stream_url(self, cid, ut_start=None):
        settings = self.read_settings_file()
        if not settings:
            self.login()
            return self.get_stream_url(cid, ut_start)

        channel = self.channels[cid]
        if ut_start is None:
            return channel.url

        ut_start = int(ut_start) - (HOUR * self.timeshift)
        program = None  # type: Program

        for p in channel.programs.values():  # type: Program
            if p.ut_start <= ut_start < p.ut_end:
                program = p
                break

        if program is not None:
            uri = "api/api_v2.php?_resource=users/%s/epg/%s/link" % \
                  (self.read_settings_file().get("user_id"), program.id)
            response = self.make_request(uri, headers=self.default_headers())
            if response.get("status") == "OK":
                return response.get("results")

        raise ApiException(get_string(TEXT_NOT_PLAYABLE_ID), Api.E_UNKNOW_ERROR)

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        programs = self.get_epg_gh(self.channels[cid])
        if len(programs):
            return programs

        settings = self.read_settings_file()
        if not settings:
            self.login()
            return self.get_epg(cid)
        start = int(time_now() - self.archive_ttl)
        end = int(time_now() + (DAY * 2))
        uri = "api/api_v2.php?_resource=users/%s/tv-channels/%s/epg&from=%s&to=%s" % \
              (settings.get("user_id"), cid, start, end)
        response = self.make_request(uri, headers=self.default_headers())
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))

        programs = OrderedDict()
        prev = None  # type: Program
        for entry in response.get("results", []):
            program = Program(
                cid,
                self.channels[cid].gid,
                entry["start"],
                entry["end"],
                entry["name"],
                "",
                bool(entry["in_archive"])
            )
            program.data["id"] = entry["id"]
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
