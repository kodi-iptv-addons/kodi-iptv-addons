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
        super(Ottclub, self).__init__(**kwargs)
        self.playlist = playlist
        self.key = key
        self.adult = adult
        self.auth_status = self.AUTH_STATUS_OK
        self.m3u_groups = OrderedDict()
        Model.API = self

        m3u = urllib2.urlopen(self.playlist).read()

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
                    self.icon_url + item["tvg-logo"],
                    bool(item["tvg-id"]),
                    bool(item["tvg-rec"]),
                    bool(item["adult"]),
                    item["url"].replace('{KEY}', self.key)
                )
                group.channels[channel.cid] = channel

        M3u8Parser().parse(m3u, on_item)

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

    def is_login_uri(self, uri):
        return False

    def login(self):
        pass

    def get_groups(self):
        return self.m3u_groups

    def get_stream_url(self, cid, ut_start=None):
        channels = self.channels
        url = channels[cid].url
        if ut_start is not None:
            url = "%s?utc=%s&lutc=%s" % (url, ut_start, int(time_now()))
        return url

    def get_epg(self, cid):
        # type: (str) -> OrderedDict[int, Program]
        programs = OrderedDict()
        response = self.make_request("channel/%s" % cid)
        if self._last_error:
            raise ApiException(self._last_error["message"], self._last_error["code"])
        prev = None
        for k in sorted(response.iterkeys()):
            v = response[k]
            program = Program(
                cid,
                self.channels[cid].gid,
                v["time"],
                v["time_to"],
                v["name"],
                v["descr"],
                bool(int(v["rec"]))
            )
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
