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
import re


class M3u8Channel(object):
    def __init__(self, name, group=None, url=None, id=None):
        self.name = unicode(name, "utf-8") if type(name) is not unicode else name
        self.group = unicode(group, "utf-8") if group and type(group) is not unicode else group
        self.url = url


class M3u8Item(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getitem__(self, item):
        return self.__dict__.get(item, None)


def reg(pattern, line):
    # type: (str, str) -> str or None
    res = re.search(pattern, line)
    return res.group(1) if res else None


class M3u8Parser(object):
    EXTM3U = '#EXTM3U'
    EXTINF = '#EXTINF'
    EXTGRP = '#EXTGRP'

    def __init__(self):
        self.channel = None
        pass

    def parse(self, content, on_item):
        # type: (str, callable()) -> None
        args = dict()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(self.EXTM3U):
                args = dict({
                    "id": self.EXTM3U,
                    "url-epg": reg('\s+url-epg\s*=\s*"([^"]+)"', line),
                    "url-logo": reg('\s+url-logo\s*=\s*"([^"]+)"', line)
                })
                on_item(M3u8Item(**args))
                args = dict()
            if line.startswith(self.EXTINF):
                if len(args) > 0:
                    on_item(M3u8Item(**args))
                options, name = line.replace(self.EXTINF + ':', '').split(',')  # type: (str, str)
                tvg_rec = reg('\s+tvg-rec\s*=\s*"([^"]+)"', line) or 0
                args = dict({
                    "id": self.EXTINF,
                    "name": name,
                    "tvg-id": reg('\s+tvg-id\s*=\s*"([^"]+)"', line),
                    "tvg-logo": reg('\s+tvg-logo\s*=\s*"([^"]+)"', line),
                    "group-title": reg('\s+group-title\s*=\s*"([^"]+)"', line),
                    "tvg-rec": int(tvg_rec),
                    "adult": reg('\s+adult\s*=\s*"([^"]+)"', line),
                })
            if line.startswith(self.EXTGRP):
                args["group-title"] = unicode(line.replace(self.EXTGRP + ':', '').strip(), "utf-8")
            if line.startswith('http'):
                args["url"] = line
                if args["tvg-id"] is None:
                    for p in args['url'].split("/"):
                        if p.isdigit():
                            args["tvg-id"] = p
                            break
                on_item(M3u8Item(**args))
                args = dict()
