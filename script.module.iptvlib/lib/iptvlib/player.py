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

from iptvlib import *
from iptvlib.models import Program
from xbmcgui import ListItem


class Player(xbmc.Player):
    program = None  # type: Program
    offset = None  # type: int
    ut_start = None  # type: int
    ut_end = None  # type: int
    on_playback_callback = None  # type: callable()
    last_known_position = None  # type: int

    def __init__(self):
        pass

    def update_last_known_position(self):
        self.last_known_position = int(self.getTime() + self.ut_start)

    @run_async
    def play(self, item=None, program=None, offset=0, on_playback_callback=None, listitem=None, windowed=False):
        # type: (str, Program, int, callable, ListItem, bool) -> None
        self.program = program
        self.offset = offset
        if self.program:
            self.ut_start = self.program.ut_start + self.offset
            self.ut_end = self.program.ut_end
        self.on_playback_callback = on_playback_callback

        if listitem is not None:
            super(Player, self).play(item=item, listitem=listitem, windowed=windowed)
        else:
            super(Player, self).play(item=item, windowed=windowed)

    def get_program(self):
        # type: () -> Program
        if not self.isPlaying():
            return self.program
        player_time = self.getTime() + self.offset if self.is_live() is False else \
            int(time_now()) - self.program.ut_start
        ut_start = self.program.ut_start
        program = self.program
        while player_time > (program.ut_end - ut_start):
            program = program.next_program
        return program

    def get_position(self):
        # type: () -> float
        if self.isPlaying() is False:
            return -1

        try:
            program = self.get_program()
            if self.is_live():
                return time_now() - program.ut_start

            if self.ut_start < program.ut_start:
                return self.getTime() - (program.ut_start - self.ut_start)

            return self.getTime() + self.offset
        except Exception, ex:
            log("Exception %s: %s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            return -1

    def get_percent(self, strict=False, adjust_secs=0):
        # type: (bool, int) -> (float, int)
        program = self.get_program()
        position = self.get_position()
        percent = secs_to_percent(program.length, position + adjust_secs)
        if strict is True:
            if percent <= 0:
                percent = 0.01
            elif percent >= 100:
                percent = 99.99
        return percent, position

    def is_live(self):
        # type: () -> bool
        return self.offset == 0

    def onPlayBackEnded(self):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackEnded")

    def onPlayBackPaused(self):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackPaused")

    def onPlayBackResumed(self):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackResumed")

    def onPlayBackSeek(self, time, seekOffset):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackSeek", time=time, seekOffset=seekOffset)

    def onPlayBackSeekChapter(self, chapter):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackSeekChapter", chapter=chapter)

    def onPlayBackSpeedChanged(self, speed):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackSpeedChanged", speed=speed)

    def onPlayBackStarted(self):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackStarted")

    def onPlayBackStopped(self):
        if callable(self.on_playback_callback):
            self.on_playback_callback(event="onPlayBackStopped")
