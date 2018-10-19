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
import traceback
import urllib2

from iptvlib.api import Api, ApiException
from iptvlib.m3u8 import M3u8Parser
from iptvlib.models import *


class Ottclub(Api):
    playlist = None  # type: str
    key = None  # type: str
    adult = None  # type: bool
    hostname = None  # type: str
    epg_url = None  # type: str
    icon_url = None  # type: str
    m3u_groups = None  # type: OrderedDict[str, Group]
    m3u_channels = None  # type: OrderedDict[str, Channel]

    def __init__(self, playlist, key, adult, **kwargs):
        # type: (str, str, bool, dict) -> None
        super(Ottclub, self).__init__(**kwargs)
        self.playlist = playlist if playlist.startswith('http') else 'http://%s/ottplayer/' % playlist
        self.key = self.username = key
        self.adult = adult
        self.auth_status = self.AUTH_STATUS_OK
        self.m3u_groups = OrderedDict()
        Model.API = self

        try:
            m3u = urllib2.urlopen(self.playlist).read()
        except urllib2.URLError, ex:
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            raise ApiException(self.playlist, Api.E_HTTP_REQUEST_FAILED, str(ex.reason).encode('utf-8'))

        def on_item(item):

            if item["id"] == M3u8Parser.EXTM3U:
                self.epg_url = item["url-epg"]
                self.icon_url = item["url-logo"]
            elif item["id"] == M3u8Parser.EXTINF:

                l = [k for k, v in self.m3u_groups.iteritems() if v.name == item["group-title"]]
                gid = l[0] if len(l) else None
                if gid is None:
                    gid = str(len(self.m3u_groups) + 1)
                    self.m3u_groups[gid] = Group(gid, item["group-title"], OrderedDict())
                group = self.m3u_groups[gid]
                if self.adult is False and bool(item["adult"]) is True:
                    return
                channel = Channel(
                    item["tvg-id"],
                    group.gid,
                    item["name"],
                    "%s%s" % (self.icon_url, item["tvg-logo"]),
                    bool(item["tvg-id"]),
                    bool(item["tvg-rec"]),
                    bool(item["adult"]),
                    item["url"].replace('{KEY}', self.key)
                )
                group.channels[channel.cid] = channel

        M3u8Parser().parse(m3u, on_item)

        if len(self.m3u_groups) == 0:
            raise ApiException(self.playlist, Api.E_UNKNOW_ERROR)

    @property
    def base_api_url(self):
        return "%s%%s" % self.epg_url

    @property
    def base_icon_url(self):
        return "%s"

    @property
    def host(self):
        return self.hostname

    @property
    def diff_live_archive(self):
        return 0

    @property
    def archive_ttl(self):
        return TREEDAYS

    def get_cookie(self):
        return ""

    def is_login_uri(self, uri, payload=None):
        return False

    def login(self):
        pass

    def get_groups(self):
        return self.m3u_groups

    def get_stream_url(self, cid, ut_start=None):
        channels = self.channels
        url = channels[cid].url
        if ut_start is not None:
            url = "%s%sutc=%s&lutc=%s" % (url, "&" if "?" in url else "?", ut_start, int(time_now()))
        return url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        programs = OrderedDict()
        response = self.make_request("channel/%s" % cid)
        if self._last_error:
            raise ApiException(
                self._last_error.get("message", get_string(TEXT_SERVICE_ERROR_OCCURRED_ID)),
                self._last_error.get("code", Api.E_UNKNOW_ERROR)
            )
        prev = None
        response = {int(k):v for k,v in response.items()}
        for k in sorted(response.iterkeys()):
            v = response[k]
            program = Program(
                cid,
                self.channels[cid].gid,
                v["time"],
                v["time_to"],
                v["name"],
                v["descr"],
                bool(v["rec"]) if v.has_key("rec") else self.channels[cid].archive
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
