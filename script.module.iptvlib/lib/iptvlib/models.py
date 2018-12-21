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
import traceback
from collections import OrderedDict

import xbmcgui
from iptvlib import *


class Model(object):
    data = None  # type: dict
    API = None

    def __init__(self, data):
        self.data = data
        self._listitem = None

    def __getattr__(self, attr):
        return self.data[attr]

    def get_icon(self):
        return ""

    def get_listitem(self):
        if self._listitem is None:
            self._listitem = xbmcgui.ListItem()
            for key, value in self.data.iteritems():
                if key == 'icon':
                    value = self.get_icon()
                if isinstance(value, (type(None), str, unicode, int, float, bool)) is False:
                    continue
                if isinstance(value, basestring) is False:
                    value = str(value)
                try:
                    value = value.decode('utf-8')
                except UnicodeError:
                    value = value.encode('utf-8')
                self._listitem.setProperty(key, value)
        return self._listitem


class Group(Model):
    gid = None  # type: str
    name = None  # type: str
    channels = None  # type: OrderedDict[str, Channel]
    number = None  # type: int

    def __init__(self, gid, name, channels, number=None):
        # type: (str, str, OrderedDict[str, Channel], int) -> Group
        self.gid = gid
        self.name = name
        self.channels = OrderedDict(channels)
        self.number = number

        super(Group, self).__init__({"gid": gid, "group_name": name, "icon": "", "number": number})

    def get_icon(self):
        return "%s.png" % (self.number if self.number is not None else self.data["gid"])

    def __repr__(self):
        return "%s (%s)" % (self.name, self.gid)


class Channel(Model):
    cid = None  # type: str
    gid = None  # type: str
    name = None  # type: str
    icon = None  # type: str
    epg = None  # type: bool
    archive = None  # type: bool
    protected = None  # type: bool
    url = None  # type: str
    _programs = None  # type: dict[int, Program]

    def __init__(self, cid, gid, name, icon, epg, archive, protected=False, url=None):
        # type: (str, str, str, str, bool, bool, bool, str) -> Channel
        self.cid = cid
        self.gid = gid
        self.name = name
        self.icon = icon
        self.epg = epg
        self.archive = archive
        self.protected = protected
        self.url = url
        self._programs = OrderedDict()
        channel_data = {
            "cid": cid,
            "gid": gid,
            "channel_name": name,
            "icon": icon,
            "epg": epg,
            "archive": archive,
            "protected": protected,
        }
        super(Channel, self).__init__(channel_data)

    def get_icon(self):
        return addon.getAddonInfo('icon') if not self.icon else self.icon

    def get_current_program(self):
        # type: () -> Program
        return self.get_program_by_time(int(time_now()))

    def get_program_by_time(self, timestamp):
        # type: (int) -> Program
        for ut_start, program in self.programs.items():
            if program.ut_start == timestamp:
                return program
            if program.ut_start > timestamp and program.prev_program is not None:
                return program.prev_program
        return Program.factory(self)

    @property
    def programs(self):
        if len(self._programs) == 0:
            try:
                real_programs = self.API.get_epg(self.cid)  # type: OrderedDict
                if len(real_programs) == 0:
                    ut_start = timestamp_to_midnight(time_now())
                    real_programs[ut_start] = Program.factory(self, ut_start, ut_start + HOUR)

                first_program = real_programs[next(iter(real_programs.iterkeys()))]  # type: Program
                last_program = real_programs[next(reversed(list(real_programs.iterkeys())))]  # type: Program

                # prepend epg with dummy entries
                if first_program.ut_start > time_now() - self.API.archive_ttl:
                    start_time = int(time_now() - self.API.archive_ttl) - DAY
                else:
                    start_time = first_program.ut_start - DAY
                start_time = timestamp_to_midnight(start_time)
                programs = Program.get_dummy_programs(self, start_time, first_program.ut_start)
                last_prepend_program = programs[next(reversed(list(programs.iterkeys())))]
                programs.update(real_programs)
                first_program.prev_program = last_prepend_program
                last_prepend_program.next_program = first_program

                # append epg with dummy entries
                if last_program.ut_end == 0:
                    last_program.ut_end = last_program.ut_start + HOUR
                end_time = timestamp_to_midnight(last_program.ut_end + DAY * 2)
                append_programs = Program.get_dummy_programs(self, last_program.ut_end, end_time)
                first_append_program = append_programs[next(iter(append_programs.iterkeys()))]  # type: Program
                programs.update(append_programs)
                last_program.next_program = first_append_program
                first_append_program.prev_program = last_program

                prev = None  # type: Program
                for key in sorted(programs.iterkeys()):
                    program = programs[key]
                    if prev:
                        program.prev_program = prev
                        program.prev_program.next_program = program
                    self._programs[key] = prev = programs[key]

            except Exception, ex:
                log("Exception %s: message=%s" % (type(ex), ex.message))
                log(traceback.format_exc(), xbmc.LOGDEBUG)
                start_time = timestamp_to_midnight(time_now() - self.API.archive_ttl - DAY)
                end_time = timestamp_to_midnight(time_now() + TWODAYS)
                self._programs = Program.get_dummy_programs(self, start_time, end_time)
        return self._programs

    def __repr__(self):
        return "%s (%s/%s)" % (self.name, self.gid, self.cid)


class Program(Model):
    cid = None  # type: str
    gid = None  # type: str
    ut_start = None  # type: int
    ut_end = None  # type: int
    length = None  # type: int
    title = None  # type: str
    descr = None  # type: str
    epg = None  # type: bool
    archive = None  # type: bool
    image = None  # type: str
    prev_program = None  # type: Program
    next_program = None  # type: Program

    @staticmethod
    def factory(channel, ut_start=None, ut_end=None, length=HOUR,
                title=get_string(TEXT_NO_INFO_AVAILABLE_ID),
                descr=get_string(TEXT_NO_INFO_AVAILABLE_ID)):
        # type: (Channel, int, int, int, str, str) -> Program
        ut_start = str_to_timestamp(format_date(time_now(), custom_format="%d%m%y%H"), "%d%m%y%H") \
            if ut_start is None else ut_start
        ut_end = ut_start + length if ut_end is None else ut_end
        return Program(channel.cid, channel.gid, int(ut_start), int(ut_end), title, descr, channel.archive)

    @staticmethod
    def get_dummy_programs(channel, start_time, end_time):
        # type: (Channel, int, int) -> OrderedDict[int, Program]
        programs = OrderedDict()
        ut_start = start_time
        prev = None
        while ut_start < end_time:
            ut_end = end_time if (ut_start + HOUR) > end_time else (ut_start + HOUR)
            program = Program.factory(channel, ut_start, ut_end)
            if prev is not None:
                program.prev_program = prev
                prev.next_program = program
            programs[program.ut_start] = prev = program
            ut_start = ut_start + HOUR
        return programs

    def __init__(self, cid, gid, ut_start, ut_end, title, descr, archive=False, image=None):
        # type: (str, str, int, int, str, str, bool, str) -> Program
        self.cid = cid
        self.gid = gid
        self.ut_start = ut_start
        self.ut_end = ut_end
        self.length = self.ut_end - self.ut_start
        self.title = title
        self.descr = descr
        self.archive = archive
        self.image = image
        program_data = {
            "cid": self.cid,
            "gid": self.gid,
            "title": self.title,
            "title_list": (self.title[:52] + '...') if len(self.title) > 55 else self.title,
            "descr": self.descr,
            "t_start": format_date(self.ut_start, custom_format="%H:%M"),
            "t_end": format_date(self.ut_end, custom_format="%H:%M"),
            "d_start": format_date(self.ut_start, custom_format="%A, %d.%m"),
            "ut_start": self.ut_start,
            "ut_end": self.ut_end
        }
        super(Program, self).__init__(program_data)

    def is_playable(self):
        # type: () -> bool
        return self.is_live_now() or self.is_archive_now()

    def is_past_now(self):
        # type: () -> bool
        return self.ut_end < time_now()

    def is_live_now(self):
        # type: () -> bool
        return self.ut_start <= time_now() <= self.ut_end

    def is_archive_now(self):
        # type: () -> bool
        now = time_now()
        return bool(self.archive) is True \
               and self.ut_end < now \
               and self.ut_start > (now - self.API.archive_ttl)

    def equals(self, other):
        # type: (Program) -> bool
        return str(self.cid) == str(other.cid) \
               and self.ut_start == other.ut_start \
               and self.ut_end == other.ut_end

    def get_listitem(self):
        listitem = Model.get_listitem(self)
        status = " "
        if self.is_past_now():
            if self.archive is True:
                status = "prg_status_archive.png"
            else:
                status = "prg_status_past.png"
        elif self.is_live_now():
            status = "prg_status_live.png"
        listitem.setProperty("status", status)
        listitem.setProperty("day_color", "1%s.png" % format_date(self.ut_start, custom_format="%w"))
        return listitem
