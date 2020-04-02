# coding=utf-8
#
#      Copyright (C) 2020 Dmitry Vinogradov
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
import hashlib
import urllib2
import urlparse

from iptvlib.api import Api, ApiException
from iptvlib.models import *
from uuid import getnode as get_mac


class TvTeam(Api):

    adult = None  # type: bool
    sort_channels = None  # type: bool
    hostname = None  # type: str
    _session_id = None  # type: str
    _random_token = None  # type: str

    def __init__(self, hostname, adult, **kwargs):
        super(TvTeam, self).__init__(**kwargs)
        self.hostname = hostname
        self.adult = adult
        self.auth_status = self.AUTH_STATUS_NONE
        Model.API = self

    @property
    def base_api_url(self):
        return "https://%s/api/%%s" % self.hostname

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
        return WEEK

    @property
    def device_id(self):
        return int(hashlib.sha256('kodi-iptv-addons-%s' % get_mac()).hexdigest(), 16) % 10 ** 8


    def get_cookie(self):
        return ""

    def is_login_request(self, uri, payload=None, method=None, headers=None):
        return uri == "" and payload.has_key("userLogin") and self._session_id is None

    def login(self):
        passwd = hashlib.md5(self.password).hexdigest()
        response = self.make_request("", {"userLogin": self.username, "userPasswd": passwd})
        if response.get("error") != "":
            raise ApiException(
                addon.getLocalizedString(TEXT_AUTHENTICATION_FAILED_ID),
                Api.E_API_ERROR
            )
        else:
            is_error, error = Api.is_error_response(response)
            if is_error:
                raise ApiException(error.get("message"), error.get("code"))

        self._session_id = response.get("data").get("sessionId")
        self.auth_status = self.AUTH_STATUS_OK
        self._random_token = self.get_random_token()
        return response

    def get_random_token(self):
        payload = {
            "apiAction": "getRandomTokens",
            "cnt": "1",
            "fingerPrint": "%d" % self.device_id,
            "sessionId": self._session_id
        }
        response = self.make_request("", payload)
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        return response.get("data").get("tokens")[0]

    def get_groups(self):
        if self._session_id is None:
            self.login()
        payload = {
            "apiAction": "getUserChannels",
            "resultType": "tree",
            "sessionId": self._session_id
        }
        response = self.make_api_request(payload)
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))
        data = response.get("data")
        groups = OrderedDict()
        channels = OrderedDict()
        for group_data in data.get("userChannelsTree"):
            gid = group_data.get("groupId")
            if gid == 0:
                continue
            group = Group(
                gid=gid,
                name=group_data.get("groupName"),
                channels=OrderedDict(),
                number=int(group_data.get("sortOrder"))
            )
            groups[gid] = group

            for channel_data in group_data.get("channelsList"):
                is_adult = bool(int(channel_data.get("isPorno")))
                if self.adult is False and is_adult is True:
                    continue

                cid = channel_data.get("channelId")
                has_epg = len(channel_data.get("curProgram").get("prTitle")) > 0
                channel = Channel(
                    cid=cid,
                    gid=group.gid,
                    name=channel_data.get("channelName"),
                    icon=channel_data.get("channelLogo"),
                    epg=has_epg,
                    archive=has_epg,
                    protected=is_adult
                )
                channel.data.update({"stream_url": channel_data["liveLink"]})
                group.channels[cid] = channels[cid] = channel
        return groups

    def get_stream_url(self, cid, ut_start=None):
        channel = self.channels[cid]
        url_info = urlparse.urlparse(channel.data.get("stream_url"))
        url = "http://%s:%s/ch%s/" % (url_info.hostname, url_info.port, cid.zfill(3))
        if ut_start is None:
            url = "%smono.m3u8?token=%s" % (url, self._random_token)
        else:
            url = "%sindex-%s-%s.m3u8?token=%s" % (url, int(ut_start), int(time_now() - ut_start), self._random_token)
        log("url: %s" % url, xbmc.LOGDEBUG)
        return url

    def resolve_url(self, url):
        # type: (str) -> str
        log("url: %s" % url, xbmc.LOGDEBUG)
        request = self.prepare_request(url)
        response = urllib2.urlopen(request)
        log("response.url: %s" % response.url, xbmc.LOGDEBUG)
        return response.url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        if self._session_id is None:
            self.login()
        payload = {
            "apiAction": "getTvProgram",
            "channelId": cid,
            "sessionId": self._session_id
        }
        response = self.make_api_request(payload)  # type: dict[str, list[dict]]
        is_error, error = Api.is_error_response(response)
        if is_error:
            raise ApiException(error.get("message"), error.get("code"))

        programs = OrderedDict()
        prev = None
        for v in response.get("data").get("tvProgram"):
            program = Program(
                cid,
                self.channels[cid].gid,
                int(v.get("prStartSec")),
                int(v.get("prStopSec")),
                v.get("prTitle"),
                v.get("prSubTitle"),
                (v.get("streamLink") != "")
            )
            program.data.update({"stream_url": v.get("streamLink")})
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs

    def make_api_request(self, payload):
        response = self.make_request("", payload)
        if response.get("error") != "":
            response = {
                "__error": {
                    "message": response.get("error"),
                    "code": self.E_UNKNOW_ERROR,
                    "details": {
                        "status": response.get("status"),
                        "query": response.get("query")
                    },
                }
            }
        return response
