import json

from iptvlib import *
from iptvlib.api import Api, ApiException
from iptvlib.models import *


class Kartina(Api):
    hostname = None  # type: str
    use_origin_icons = None  # type: bool
    _queue = None  # type: Queue

    def __init__(self, hostname, use_origin_icons, **kwargs):
        super(Kartina, self).__init__(**kwargs)
        self.hostname = hostname
        self.use_origin_icons = use_origin_icons

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
        return TWOWEEKS

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

        groups = dict()
        for group_data in response["groups"]:
            if all(k in group_data for k in ("id", "name", "channels")) is False:
                continue
            channels = dict()
            for channel_data in group_data["channels"].values():
                if channel_data.is_video is False:
                    continue
                channel_data["cid"] = str(channel_data["cid"])
                group_data["id"] = str(group_data["id"])
                channel = Channel(
                    cid=channel_data["cid"],
                    gid=group_data["id"],
                    name=channel_data["name"],
                    icon=channel_data["icon"],
                    epg=True if int(channel_data["epg_start"]) > 0 else False,
                    archive=bool(channel_data["have_archive"])
                )
                channels[channel.cid] = channel
            groups[group_data["id"]](Group(group_data["id"], group_data["name"], channels))
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

    def get_epg(self, channel):
        # type: (str) -> OrderedDict[int, Program]
        urls = list()
        days = (self.archive_ttl / DAY) + 5
        start = int(time_now() - self.archive_ttl)
        for i in range(days):
            day = format_date(start + (i * DAY), custom_format="%d%m%y")
            url = "https://iptvlib.kartina.tv/api/json/open_epg?period=day&cid=%s&dt=%s" % (channel.cid, day)
            urls.append(url)

        results = download(urls)

        epg = dict()
        prev_ts = None
        for key in sorted(results.iterkeys()):
            try:
                response = results[key]
                if response.status == 200:
                    content = json.loads(response.read())
                    for entry in content["report"][0]["list"]:
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
                            epg[prev_ts]["duration"] = ts - epg[prev_ts]["time"]
                        prev_ts = ts
            except:
                pass

        programs = dict()
        prev = None  # type: Program
        for key in sorted(epg.iterkeys()):
            val = epg[key]
            program = Program.factory(channel, val["time"], val["time_to"], val["duration"], val["name"], val["descr"])
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
        return programs
