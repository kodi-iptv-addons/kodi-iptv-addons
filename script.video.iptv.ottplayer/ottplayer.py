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
import urllib2

from iptvlib.api import Api, ApiException, HttpRequest
from iptvlib.models import *


class Ottplayer(Api):
    TEXT_NO_PLAYLIST_BOUND_ID = 30007  # type: int
    TEXT_YOU_CAN_BIND_DEVICE_ID = 30008  # type: int

    DEVICE_TYPE = "KODI"

    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    adult = None  # type: bool

    _device_id = None  # type: str
    _api_calls = None  # type: list[str]
    _utc_local_offset = None  # type: float

    def __init__(self, hostname, adult, **kwargs):
        super(Ottplayer, self).__init__(**kwargs)
        self.hostname = hostname
        self.adult = adult
        self._api_calls = 0
        self._utc_local_offset = math.ceil(calendar.timegm(time.localtime()) - time.time())
        Model.API = self

    @property
    def base_api_url(self):
        return "https://%s/api/v1.0/%%s" % self.host

    @property
    def base_icon_url(self):
        return "%%s"

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
        return payload is not None and "login" in payload.get("method", "")

    @staticmethod
    def raise_api_exception_on_error(error):
        if not error:
            return
        raise ApiException(error, Api.E_API_ERROR)

    def prepare_api_request(self, method, params, sid_index=-1, ident=None):
        # type: (str, list, int, str) -> HttpRequest
        self._api_calls += 1
        if sid_index >= 0:
            params.insert(sid_index, self.read_cookie_file())
        ident = ident or "%s:%s" % (method, self._api_calls)
        payload = {"id": self._api_calls, "method": method, "params": params, }
        return self.prepare_request("", payload, "POST", {"Content-Type": "application/json"}, ident)

    def make_api_request(self, method, params, sid_index=-1):
        # type: (str, list, int) -> dict
        request = self.prepare_api_request(method, params, sid_index)
        return self.send_request(request)

    def do_login(self, device_id=""):
        response = self.make_api_request("login", [self.username, self.password, device_id])
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        Ottplayer.raise_api_exception_on_error(response["error"])
        return response

    def login(self):
        if self._device_id is None:
            response = self.do_login()
            self.auth_status = self.AUTH_STATUS_OK
            self.write_cookie_file("%s" % (response["result"]))
            devices = self.get_devices()
            found = False
            for device in devices:
                if device.get("name") == self.DEVICE_TYPE:
                    self._device_id = device.get("key")
                    found = True
                    break

            if found is False:
                self._device_id = self.register_device()

        response = self.do_login(self._device_id)
        self.auth_status = self.AUTH_STATUS_OK
        self.write_cookie_file("%s" % (response["result"]))
        return response

    def get_devices(self):
        # type: () -> list[dict]
        response = self.make_api_request("get_devices", ["unknown"], 1)
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        Ottplayer.raise_api_exception_on_error(response["error"])
        return response["result"]

    def register_device(self):
        # type: () -> str
        response = self.make_api_request("register_device", [self.DEVICE_TYPE, "unknown"], 2)
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(
                error.get("message", get_string(TEXT_HTTP_REQUEST_ERROR_ID)),
                error.get("code", Api.E_UNKNOW_ERROR)
            )
        if "error" in response and response["error"]:
            raise ApiException(response["error"], Api.E_API_ERROR)
        return response["result"]

    def get_groups(self):
        if self.auth_status != self.AUTH_STATUS_OK:
            self.login()
        get_groups_request = self.prepare_api_request("get_groups", [], 0)
        get_playlists_request = self.prepare_api_request("get_playlists", [], 0)
        requests = [get_groups_request, get_playlists_request]
        results = self.send_parallel_requests(requests)

        get_groups_response = results[get_groups_request.ident]
        is_error, error = Api.is_error_response(get_groups_response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        Ottplayer.raise_api_exception_on_error(get_groups_response["error"])

        groups = OrderedDict()
        number = 1
        for group_data in get_groups_response["result"]:
            if all(k in group_data for k in ("id", "name", "title")) is False:
                continue
            gid = str(group_data["id"])
            groups[gid] = Group(gid, group_data["title"], OrderedDict(), number)
            number += 1

        get_playlists_response = results[get_playlists_request.ident]
        is_error, error = Api.is_error_response(get_playlists_response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        Ottplayer.raise_api_exception_on_error(get_playlists_response["error"])

        playlists = get_playlists_response.get("result")  # type: list[dict]
        if len(playlists) == 0:
            raise ApiException("%s\n%s" % (
                addon.getLocalizedString(self.TEXT_NO_PLAYLIST_BOUND_ID),
                addon.getLocalizedString(self.TEXT_YOU_CAN_BIND_DEVICE_ID)
            ), Api.E_UNKNOW_ERROR)

        channels = OrderedDict()
        requests = []
        for playlist in playlists:
            requests.append(self.prepare_api_request("get_channels", [playlist.get("id")], 0, playlist.get("id")))

        results = self.send_parallel_requests(requests)
        for playlist_id, result in results.iteritems():
            is_error, error = Api.is_error_response(result)
            if is_error:
                raise ApiException(error.get("message"), error.get("code"))
            Ottplayer.raise_api_exception_on_error(result["error"])
            for channel_data in result["result"]:
                if self.adult is False and bool(channel_data.get("adult", False)) is True:
                    continue
                playlist = next((playlist for playlist in playlists if playlist.get("id") == playlist_id), {})
                cid = "%s-%s" % (channel_data["group_id"], channel_data["id"],)
                channel = Channel(
                    cid=cid,
                    gid=str(channel_data["group_id"]),
                    name=channel_data["name"],
                    icon=channel_data["pict"],
                    epg=True if channel_data["epg_id"] > 0 else False,
                    archive=playlist.get("have_archive", False),
                    protected=bool(channel_data.get("adult", False)),
                    url=channel_data["href"]
                )
                channel.data['epg_id'] = channel_data["epg_id"]
                group_id = str(channel_data["group_id"])
                if groups.has_key(group_id) is False:
                    continue
                groups[group_id].channels[channel.cid] = channels[channel.cid] = channel
        return groups

    def get_stream_url(self, cid, ut_start=None):
        channels = self.channels
        url = channels[cid].url
        if ut_start is not None:
            # url = "%s%sarchive=%s&archive_end=%s" % (url, "&" if "?" in url else "?", ut_start, int(time_now()))
            url = "%s%sutc=%s&lutc=%s" % (url, "&" if "?" in url else "?", ut_start, int(time_now()))
        return self.resolve_url(url)

    def resolve_url(self, url):
        request = self.prepare_request(url)
        response = urllib2.urlopen(request)
        return response.url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        channel = self.channels[cid]
        programs = self.get_epg_gh(channel)
        if len(programs):
            return programs

        response = self.make_api_request("get_epg2", [channel.epg_id, 2, int(self.archive_ttl / DAY)])
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        Ottplayer.raise_api_exception_on_error(response["error"])

        epg = dict()
        for v in response["result"]:
            start = int(str_to_timestamp(v["start"], "%Y-%m-%d %H:%M:%S") + self._utc_local_offset)
            stop = int(str_to_timestamp(v["stop"], "%Y-%m-%d %H:%M:%S") + self._utc_local_offset)
            epg[start] = dict({
                "time": start,
                "time_to": stop,
                "duration": stop - start,
                "name": v["title"],
                "descr": v["desc"]
            })

        programs = OrderedDict()
        prev = None  # type: Program
        for key in sorted(epg.iterkeys()):
            val = epg[key]
            program = Program(
                cid,
                channel.gid,
                val["time"],
                val["time_to"],
                val["name"],
                val["descr"],
                channel.archive
            )
            if prev is not None:
                if program.ut_start != prev.ut_end:
                    continue
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
