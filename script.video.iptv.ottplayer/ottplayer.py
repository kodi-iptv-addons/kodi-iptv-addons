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


class Ottplayer(Api):
    ALL_CHANNELS_GROUP_ID = 12036621  # type: int
    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    adult = None  # type: bool
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
        return HALFHOUR

    @property
    def archive_ttl(self):
        return TREEDAYS

    def get_cookie(self):
        return ""

    def is_login_uri(self, uri, payload=None):
        return payload is not None and "login" in payload.get("method", "")

    def make_request_api(self, method, params, sid_index=-1):
        self._api_calls += 1
        if sid_index >= 0:
            params.insert(sid_index, self.read_cookie_file())
        payload = {"id": self._api_calls, "method": method, "params": params, }
        return self.make_request("", payload, "POST", {"Content-Type": "application/json"})

    def login(self):
        response = self.make_request_api("login", [self.username, self.password, ""])
        self.auth_status = self.AUTH_STATUS_OK
        self.write_cookie_file("%s" % (response["result"]))
        return response

    def get_groups(self):
        response = self.make_request_api("get_groups", [], 0)
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])

        groups = OrderedDict()
        nummer = 1
        for group_data in response["result"]:
            if all(k in group_data for k in ("id", "name", "title")) is False:
                continue
            gid = str(group_data["id"])
            groups[gid] = Group(gid, group_data["name"], OrderedDict(), nummer)
            nummer += 1

        response = self.make_request_api("get_channels", [self.ALL_CHANNELS_GROUP_ID], 0)
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])

        channels = OrderedDict()
        for channel_data in response["result"]:
            if self.adult is False and bool(channel_data.get("adult", False)) is True:
                continue
            channel = Channel(
                cid=str(channel_data["id"]),
                gid=str(channel_data["group_id"]),
                name=channel_data["name"],
                icon=channel_data["pict"],
                epg=True if channel_data["epg_id"] > 0 else False,
                archive=True,
                protected=bool(channel_data.get("adult", False)),
                url=channel_data["href"]
            )
            channel.data['epg_id'] = channel_data["epg_id"]
            groups[str(channel_data["group_id"])].channels[channel.cid] = channels[channel.cid] = channel
        return groups

    def get_stream_url(self, cid, ut_start=None):
        log("#### get_stream_url(cid: %s, ut_start: %s)" % (cid, ut_start))
        channels = self.channels
        url = channels[cid].url
        if ut_start is not None:
            url = "%s?utc=%s&lutc=%s" % (url, ut_start, int(time_now()))
        return url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        channel = self.channels[cid]
        response = self.make_request_api("get_epg2", [channel.epg_id, 2, int(self.archive_ttl / DAY)])
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])

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


if __name__ == "__main__":
    o = Ottplayer(hostname='api.ottplayer.es:9000', username='dmitri.vinogradov@gmail.com', password='k1tchens69',
                  adult=False)

    response = o.login()

    groups = o.groups

    cid = o.channels.keys()[0]

    channel = o.channels['2']

    programs = channel.programs

    print "%s" % response
