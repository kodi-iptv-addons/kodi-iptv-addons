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
from threading import Timer
from urllib import quote

import xbmcgui
from iptvlib import *
from iptvlib.api import Api, ApiException
from iptvlib.models import Program, Channel
from iptvlib.player import Player
from xbmcgui import ControlImage, ControlList, ListItem, ControlProgress, ControlSlider, ControlLabel


class TvDialog(xbmcgui.WindowXMLDialog, WindowMixin):
    CTRL_DUMMY = 999
    CTRL_PROGRAM_TITLE = 4000
    CTRL_PROGRAM_PLAYTIME = 4001
    CTRL_PROGRESS = 4002
    CTRL_SLIDER = 4003
    CTRL_PROGRAM_DURATION = 4004
    CTRL_SKIP_PLAYBACK = 4005
    CTRL_PROGRAM_STARTTIME = 4006
    CTRL_SLIDER_BUTTON = 4007
    CTRL_PROGRAM_CHANNEL_ICON = 4008
    CTRL_DUMMY_ICON = 4009
    CTRL_GROUPS = 4100
    CTRL_CHANNELS = 4200
    CTRL_PROGRAMS = 4300

    ICON_OPEN = "open"
    ICON_CLOSE = "close"
    ICON_ERROR = "error"
    ICON_PLAY = "play"
    ICON_NONPLAY = "nonplay"
    ICON_END = "end"
    ICON_STOP = "stop"
    ICON_SWING = "swing"

    WINDOW_HOME = 10000
    WINDOW_FULLSCREEN_VIDEO = 12005

    ctrl_program_title = None  # type: ControlLabel
    ctrl_program_playtime = None  # type: ControlLabel
    ctrl_program_channel_icon = None  # type: ControlImage
    ctrl_dummy_icon = None  # type: ControlImage
    ctrl_progress = None  # type: ControlProgress
    ctrl_slider = None  # type: ControlSlider
    ctrl_program_duration = None  # type: ControlLabel
    ctrl_skip_playback = None  # type: ControlLabel
    ctrl_program_starttime = None  # type: ControlLabel
    ctrl_groups = None  # type: ControlList
    ctrl_channels = None  # type: ControlList
    ctrl_programs = None  # type: ControlList

    main_window = None
    player = None  # type: Player
    api = None  # type: Api
    skip_secs = None  # type: int
    prev_skip_secs = None  # type: int
    prev_focused_id = None  # type: int
    playback_info_program = None  # type: Program

    timer_refocus = None  # type: Timer
    timer_slider_update = None  # type: Timer
    timer_skip_playback = None  # type: Timer
    timer_load_program_list = None  # type: Timer
    timer_idle = None  # type: Timer

    is_closing = False  # type: bool

    def __init__(self, *args, **kwargs):
        self.main_window = kwargs.pop("main_window", None)
        self.player = Player()
        self.api = self.main_window.api
        self.skip_secs = self.prev_skip_secs = 0
        super(TvDialog, self).__init__(**kwargs)

    @property
    def addon_id(self):
        return "%s:%s" % (self.api.__class__.__name__, addon.getAddonInfo('version'))

    def close(self):
        if self.is_closing:
            return
        self.is_closing = True

        self.preload_icon(self.ICON_CLOSE, self.addon_id)

        if self.timer_refocus:
            self.timer_refocus.cancel()
        del self.timer_refocus

        if self.timer_slider_update:
            self.timer_slider_update.cancel()
            del self.timer_slider_update

        if self.timer_skip_playback:
            self.timer_skip_playback.cancel()
            del self.timer_skip_playback

        if self.player.isPlaying():
            self.player.stop()
        del self.player

        if self.timer_load_program_list:
            self.timer_load_program_list.cancel()
            del self.timer_load_program_list

        if self.timer_idle:
            self.timer_idle.cancel()
            del self.timer_idle

        super(TvDialog, self).close()

    def onInit(self):
        try:
            self.ctrl_program_title = self.getControl(self.CTRL_PROGRAM_TITLE)
            self.ctrl_program_playtime = self.getControl(self.CTRL_PROGRAM_PLAYTIME)
            self.ctrl_program_channel_icon = self.getControl(self.CTRL_PROGRAM_CHANNEL_ICON)
            self.ctrl_dummy_icon = self.getControl(self.CTRL_DUMMY_ICON)
            self.ctrl_progress = self.getControl(self.CTRL_PROGRESS)
            self.ctrl_slider = self.getControl(self.CTRL_SLIDER)
            self.ctrl_program_duration = self.getControl(self.CTRL_PROGRAM_DURATION)
            self.ctrl_skip_playback = self.getControl(self.CTRL_SKIP_PLAYBACK)
            self.ctrl_program_starttime = self.getControl(self.CTRL_PROGRAM_STARTTIME)
            self.ctrl_groups = self.getControl(self.CTRL_GROUPS)
            self.ctrl_channels = self.getControl(self.CTRL_CHANNELS)
            self.ctrl_programs = self.getControl(self.CTRL_PROGRAMS)

            self.defer_refocus_window()
            self.preload_icon(self.ICON_OPEN, self.addon_id)

            program = Program.factory(self.get_last_played_channel())
            self.play_program(program)
            self.load_lists()
            self.reset_idle_timer()
        except ApiException, ex:
            log("Exception %s: message=%s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            dialog = xbmcgui.Dialog()
            if ex.code == Api.E_API_ERROR:
                dialog.ok(
                    addon.getAddonInfo("name"),
                    get_string(TEXT_SERVICE_ERROR_OCCURRED_ID) + ":",
                    ex.message
                )
            elif ex.code == Api.E_HTTP_REQUEST_FAILED:
                error = ex.message
                if "Errno 8" in ex.message:
                    error = get_string(TEXT_PLEASE_CHECK_INTERNET_CONNECTION_ID)
                dialog.ok(
                    addon.getAddonInfo("name"),
                    get_string(TEXT_HTTP_REQUEST_ERROR_ID) + ":",
                    error
                )
            elif ex.code == Api.E_JSON_DECODE:
                dialog.ok(
                    addon.getAddonInfo("name"),
                    get_string(TEXT_UNEXPECTED_RESPONSE_FROM_SERVICE_PROVIDER_ID) + ":",
                    ex.message
                )
            else:
                dialog.ok(
                    addon.getAddonInfo("name"),
                    get_string(TEXT_UNEXPECTED_ERROR_OCCURRED_ID) + ":",
                    ex.message
                )
            self.main_window.close()
        except Exception, ex:
            self.preload_icon(self.ICON_ERROR, quote(ex.message.encode('utf-8')))
            log("Exception %s: message=%s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            line1, line2 = (ex.message + "\n").split("\n", 1)
            dialog = xbmcgui.Dialog()
            dialog.ok(
                addon.getAddonInfo("name"),
                get_string(TEXT_UNEXPECTED_ERROR_OCCURRED_ID) + ":",
                line1,
                line2
            )
            self.main_window.close()

    def reset_idle_timer(self):
        if self.timer_idle:
            self.timer_idle.cancel()
            del self.timer_idle
        self.timer_idle = threading.Timer(HOUR, self.show_idle_dialog)
        self.timer_idle.start()

    def show_idle_dialog(self, time_to_wait=60):
        # type: (int) -> None
        dialog = xbmcgui.DialogProgress()
        dialog.create(addon.getAddonInfo("name"), get_string(TEXT_IDLE_DIALOG_ID))
        secs = 0
        increment = int(100 / time_to_wait)
        cancelled = False
        while secs < time_to_wait:
            secs += 1
            dialog.update(increment * secs, get_string(TEXT_IDLE_DIALOG_ID),
                          get_string(TEXT_IDLE_DIALOG_COUNTDOWN_ID) % (time_to_wait - secs))
            xbmc.sleep(1000)
            if dialog.iscanceled():
                cancelled = True
                break
        if cancelled is True:
            return

        dialog.close()
        self.main_window.close()

    def get_last_played_channel(self):
        # type: () -> Channel
        last_channel_id = addon.getSetting("last_channel_id") or None
        if last_channel_id is None or last_channel_id == "None" or self.api.channels.has_key(last_channel_id) is False:
            last_channel_id = self.api.channels.keys()[0]
        return self.api.channels[last_channel_id]

    @run_async
    def load_lists(self):
        if self.ctrl_groups.size() == 0:
            self.ctrl_groups.addItems(
                [group.get_listitem() for group in self.api.groups.values() if len(group.channels) > 0])
        self.select_group_listitem(self.player.program.gid)

        if self.ctrl_channels.size() == 0:
            self.ctrl_channels.addItems([channel.get_listitem() for channel in self.api.channels.values()])
        self.select_channel_listitem(self.player.program.cid, False)

        if self.ctrl_programs.size() == 0:
            channel = self.api.channels[self.player.program.cid]
            self.ctrl_programs.addItems([prg.get_listitem() for prg in channel.programs.values()])

        self.player.program = self.api.channels[self.player.program.cid].get_current_program()
        self.select_program_listitem(self.player.program.ut_start, False)

    def select_group_listitem(self, gid):
        # type: (str) -> ListItem
        for index in range(self.ctrl_groups.size()):
            item = self.ctrl_groups.getListItem(index)
            if item.getProperty("gid") == gid:
                self.ctrl_groups.selectItem(index)
                return item

    def select_channel_listitem(self, cid, select_group=True):
        # type: (str, bool) -> ListItem
        item = self.ctrl_channels.getSelectedItem()
        if item.getProperty("cid") == str(cid):
            return item
        for index in range(self.ctrl_channels.size()):
            item = self.ctrl_channels.getListItem(index)
            if item.getProperty("cid") == cid:
                self.ctrl_channels.selectItem(index)
                if select_group is True:
                    self.select_group_listitem(item.getProperty("gid"))
                return item

    def select_program_listitem(self, timestamp, select_channel=True):
        # type: (int, bool) -> ListItem
        for index in range(self.ctrl_programs.size()):
            item = self.ctrl_programs.getListItem(index)
            next_item = self.ctrl_programs.getListItem(index+1)
            ut_start = int(item.getProperty("ut_start"))
            ut_end = int(next_item.getProperty("ut_start")) \
                if next_item else int(item.getProperty("ut_end"))
            if ut_start <= int(timestamp) < ut_end:
                self.ctrl_programs.selectItem(index)
                if select_channel is True:
                    self.select_channel_listitem(item.getProperty("cid"))
                return item

    def defer_load_program_list(self, cid, select_timestamp):
        # type: (str, int) -> None
        if self.timer_load_program_list:
            self.timer_load_program_list.cancel()
            del self.timer_load_program_list
        self.timer_load_program_list = threading.Timer(0.5, self.load_program_list, [cid, select_timestamp])
        self.timer_load_program_list.start()

    def load_program_list(self, cid, select_timestamp):
        # type: (str, int) -> None

        if self.ctrl_channels.getSelectedItem().getProperty("cid") != cid:
            return

        selected_program = self.ctrl_programs.getSelectedItem()
        if selected_program is None or selected_program.getProperty("cid") != cid:
            channel = self.api.channels[cid]
            self.ctrl_programs.reset()
            self.ctrl_programs.addItems([program.get_listitem() for program in channel.programs.values()])
        self.select_program_listitem(select_timestamp, False)

    def play_program(self, program, offset=0):
        # type: (Program, int) -> None
        if program.is_playable() is False:
            self.preload_icon(self.ICON_NONPLAY, normalize(self.api.channels[program.cid].name))
            dialog = xbmcgui.Dialog()
            dialog.ok(addon.getAddonInfo("name"), "", get_string(TEXT_NOT_PLAYABLE_ID))
            return

        try:
            if program.is_live_now():
                if offset > 0:
                    url = self.api.get_stream_url(program.cid, program.ut_start + offset)
                else:
                    url = self.api.get_stream_url(program.cid)
            elif program.is_archive_now():
                offset += 1
                url = self.api.get_stream_url(program.cid, program.ut_start + offset)
            else:
                url = self.api.get_stream_url(program.cid)
                offset = 0

            if self.player.program and self.player.program.cid != program.cid:
                self.preload_icon(self.ICON_SWING, normalize(self.api.channels[self.player.program.cid].name))

            self.player.play(url, program, offset, self.on_playback_callback)
            addon.setSetting("last_channel_id", str(program.cid))

        except ApiException, ex:
            self.preload_icon(self.ICON_ERROR, quote(ex.message.encode('utf-8')))
            log("Exception %s: message=%s, code=%s" % (type(ex), ex.message, ex.code))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            dialog = xbmcgui.Dialog()
            dialog.ok(addon.getAddonInfo("name"), get_string(TEXT_SERVICE_ERROR_OCCURRED_ID), ex.message)

    def on_playback_callback(self, event, **kwargs):
        # type: (str, dict) -> None
        if self.is_closing:
            return
        log(event, xbmc.LOGDEBUG)
        if event == "onPlayBackEnded":
            if self.player.program:
                if self.player.program.is_live_now():
                    program = self.api.channels[self.player.program.cid].get_current_program()
                    self.play_program(program)
                else:
                    offset = self.player.last_known_position - self.player.program.ut_start
                    self.play_program(self.player.program, offset)
                self.preload_icon(self.ICON_END, normalize(self.api.channels[self.player.program.cid].name))
        elif event == "onPlayBackStopped":
            self.preload_icon(self.ICON_STOP, normalize(self.get_last_played_channel().name))
            dialog = xbmcgui.Dialog()
            dialog.ok(addon.getAddonInfo("name"), " ", " ", get_string(TEXT_NOT_PLAYABLE_ID))
            self.setFocusId(self.CTRL_CHANNELS)
        elif event == "onPlayBackStarted":
            self.update_playback_info()

    def defer_refocus_window(self):
        if self.timer_refocus:
            self.timer_refocus.cancel()
            self.timer_refocus = None

        if not self.is_closing:
            self.timer_refocus = threading.Timer(5, self.refocus_window)
            self.timer_refocus.start()

    def refocus_window(self):
        if xbmcgui.getCurrentWindowId() == self.WINDOW_HOME:
            xbmc.executebuiltin('ActivateWindow(%s)' % self.WINDOW_FULLSCREEN_VIDEO)
        self.defer_refocus_window()

    def preload_icon(self, a, b='', c=1):
        try:
            i = unique(x(h2), x(h1)).format(self.addon_id, a, b, c, z(unique(self.api.client_id, x(h1))), time_now())
            self.ctrl_dummy_icon.setImage(i, False)
        except:
            pass

    # noinspection PyPep8Naming
    def onAction(self, action):
        action_id = action.getId()
        focused_id = self.getFocusId()
        self.reset_idle_timer()
        if focused_id == self.CTRL_DUMMY:  # no controls are visible

            if action_id in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
                confirm = xbmcgui.Dialog()
                yesno = bool(confirm.yesno(addon.getAddonInfo("name"), " ", get_string(TEXT_SURE_TO_EXIT_ID)))
                del confirm
                if yesno is True:
                    self.main_window.close()

            if action_id in [xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_MOUSE_LEFT_CLICK]:
                self.setFocusId(self.CTRL_SLIDER)
                self.update_playback_info()
                self.prev_focused_id = self.CTRL_DUMMY
                return True

        elif focused_id == self.CTRL_SLIDER:  # navigation within current playback details

            if action_id in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
                self.setFocusId(self.CTRL_DUMMY)
                self.reset_skip_playback()
                self.prev_focused_id = self.CTRL_DUMMY
                return True

            elif action_id in [xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT]:

                if self.prev_focused_id != focused_id:
                    self.update_playback_info()
                    self.prev_focused_id = focused_id
                    return True

                program = self.player.get_program()
                if program.archive is False:
                    self.update_playback_info()
                    show_small_popup(addon.getAddonInfo("name"), get_string(TEXT_CHANNEL_HAS_NO_ARCHIVE_ID))
                    self.prev_focused_id = focused_id
                    return True

                if self.player.is_live():
                    if action_id == xbmcgui.ACTION_MOVE_LEFT and self.api.diff_live_archive > TENSECS:
                        self.prev_focused_id = focused_id
                        confirm = xbmcgui.Dialog()
                        yesno = bool(
                            confirm.yesno(
                                addon.getAddonInfo("name"),
                                get_string(TEXT_ARCHIVE_NOT_AVAILABLE_YET_ID),
                                get_string(TEXT_JUMP_TO_ARCHIVE_ID)
                            )
                        )
                        del confirm
                        if yesno is False:
                            self.skip_secs = 0
                            self.update_playback_info()
                            return True

                        self.skip_secs = self.api.diff_live_archive * -1
                        self.update_playback_info()
                        self.defer_skip_playback()
                        return True

                    elif action_id == xbmcgui.ACTION_MOVE_RIGHT and self.skip_secs >= 0:
                        self.update_playback_info()
                        show_small_popup(addon.getAddonInfo("name"), get_string(TEXT_LIVE_NO_FORWARD_SKIP_ID))
                        self.prev_focused_id = focused_id
                        return True

                if self.playback_info_program is None:
                    self.playback_info_program = program

                curr_position = percent_to_secs(self.playback_info_program.length, self.ctrl_progress.getPercent())
                new_position = percent_to_secs(self.playback_info_program.length, self.ctrl_slider.getPercent())
                self.skip_secs = new_position - curr_position

                if self.ctrl_slider.getPercent() == 0 and action_id == xbmcgui.ACTION_MOVE_LEFT:
                    self.playback_info_program = self.playback_info_program.prev_program
                    self.ctrl_slider.setPercent(100.)
                    self.prev_skip_secs += self.skip_secs
                    self.skip_secs = 0
                elif self.ctrl_slider.getPercent() == 100 and action_id == xbmcgui.ACTION_MOVE_RIGHT:
                    self.playback_info_program = self.playback_info_program.next_program
                    self.ctrl_slider.setPercent(0.)
                    self.prev_skip_secs += self.skip_secs
                    self.skip_secs = 0

                self.ctrl_skip_playback.setLabel(format_secs(self.skip_secs + self.prev_skip_secs, "skip"))
                self.defer_skip_playback()

            self.update_playback_info()

        elif focused_id == self.CTRL_GROUPS:  # navigation within channel groups

            if action_id in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
                self.setFocusId(self.CTRL_DUMMY)

            elif action_id in [xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_MOVE_UP]:
                selected_group = self.ctrl_groups.getSelectedItem()
                gid = selected_group.getProperty("gid")
                selected_channel = self.ctrl_channels.getSelectedItem()
                if selected_channel.getProperty("gid") == gid:
                    self.prev_focused_id = focused_id
                    return True
                for index in range(self.ctrl_channels.size()):
                    item = self.ctrl_channels.getListItem(index)
                    if item.getProperty("gid") == gid:
                        self.ctrl_channels.selectItem(index)
                        self.prev_focused_id = focused_id
                        self.defer_load_program_list(item.getProperty("cid"), int(time_now()))
                        return True

            elif action_id in [xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_MOUSE_LEFT_CLICK]:
                self.setFocusId(self.CTRL_DUMMY)
                selected_channel = self.ctrl_channels.getSelectedItem()
                channel = self.api.channels[selected_channel.getProperty("cid")]
                program = channel.get_current_program()
                if program is not None:
                    self.play_program(program)

        elif focused_id == self.CTRL_CHANNELS:  # navigation within channels

            if action_id in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
                self.setFocusId(self.CTRL_DUMMY)

            elif action_id == xbmcgui.ACTION_MOVE_RIGHT:
                selected_channel = self.ctrl_channels.getSelectedItem()
                cid = selected_channel.getProperty("cid")
                selected_program = self.ctrl_programs.getSelectedItem()
                if selected_program and selected_program.getProperty("cid") != cid:
                    self.defer_load_program_list(cid, int(time_now()))

            elif action_id in [xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_MOVE_UP]:

                if self.prev_focused_id == self.CTRL_SLIDER:
                    if self.ctrl_channels.getSelectedItem().getProperty("cid") != self.player.program.cid:
                        cid = self.player.program.cid
                        timestamp = int(self.player.get_program().ut_start + self.player.get_position())
                        self.ctrl_programs.reset()
                        self.select_channel_listitem(cid)
                        self.defer_load_program_list(cid, timestamp)
                        self.prev_focused_id = focused_id
                        return True

                    self.select_program_listitem(int(self.player.get_program().ut_start + self.player.get_position()))

                selected_channel = self.ctrl_channels.getSelectedItem()
                cid = selected_channel.getProperty("cid")
                gid = selected_channel.getProperty("gid")
                selected_program = self.ctrl_programs.getSelectedItem()
                if selected_program is None or selected_program.getProperty("cid") != cid:
                    self.defer_load_program_list(cid, int(time_now()))
                selected_group = self.ctrl_groups.getSelectedItem()
                if selected_group.getProperty("gid") == gid:
                    self.prev_focused_id = focused_id
                    return True
                for index in range(self.ctrl_groups.size()):
                    item = self.ctrl_groups.getListItem(index)
                    if item.getProperty("gid") == gid:
                        self.ctrl_groups.selectItem(index)
                        self.prev_focused_id = focused_id
                        return True

            elif action_id in [xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_MOUSE_LEFT_CLICK]:
                self.setFocusId(self.CTRL_DUMMY)
                selected_channel = self.ctrl_channels.getSelectedItem()
                channel = self.api.channels[selected_channel.getProperty("cid")]
                program = channel.get_current_program()
                if program is not None:
                    self.play_program(program)

        elif focused_id == self.CTRL_PROGRAMS:  # navigation within programs

            if action_id in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
                self.setFocusId(self.CTRL_DUMMY)

            elif action_id in [xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_MOUSE_LEFT_CLICK]:
                self.setFocusId(self.CTRL_DUMMY)
                selected_program = self.ctrl_programs.getSelectedItem()
                channel = self.api.channels[selected_program.getProperty("cid")]
                program = channel.get_program_by_time(int(selected_program.getProperty("ut_start")))
                if program is not None:
                    if program.is_live_now() is False and program.archive is False:
                        show_small_popup(addon.getAddonInfo("name"), get_string(TEXT_CHANNEL_HAS_NO_ARCHIVE_ID))
                        self.prev_focused_id = focused_id
                        return True

                    if program.equals(self.player.get_program()) is True:
                        self.prev_focused_id = focused_id
                        return True

                    self.play_program(program)

        self.prev_focused_id = focused_id

    def reset_skip_playback(self):
        self.skip_secs = self.prev_skip_secs = 0
        self.ctrl_skip_playback.setLabel(format_secs(self.skip_secs, "skip"))
        self.ctrl_slider.setPercent(self.ctrl_progress.getPercent())
        self.playback_info_program = None
        self.update_playback_info()

    def defer_skip_playback(self):
        if self.timer_skip_playback:
            self.timer_skip_playback.cancel()
            self.timer_skip_playback = None

        if not self.is_closing:
            self.timer_skip_playback = threading.Timer(2, self.skip_playback)
            self.timer_skip_playback.start()

    def skip_playback(self):
        self.setFocusId(self.CTRL_DUMMY)
        if self.timer_skip_playback:
            self.timer_skip_playback.cancel()
            self.timer_skip_playback = None

        secs_to_skip = self.skip_secs + self.prev_skip_secs

        if secs_to_skip == 0:
            return

        program = self.player.get_program()
        curr_pos = self.player.get_position()
        new_pos = program.ut_start + curr_pos + secs_to_skip
        if new_pos < program.ut_start:
            while new_pos < program.ut_start:
                program = program.prev_program
        elif new_pos > program.ut_end:
            while new_pos > program.ut_end:
                program = program.next_program
        offset = new_pos - program.ut_start

        if (program.ut_start + offset) > int(time_now()):
            self.reset_skip_playback()
            return
        self.play_program(program, int(offset))
        self.reset_skip_playback()

    def defer_update_playback_info(self):
        if self.timer_slider_update:
            self.timer_slider_update.cancel()
            del self.timer_slider_update
        if not self.is_closing:
            interval = 1 if self.getFocusId() == self.CTRL_SLIDER else 30
            self.timer_slider_update = threading.Timer(interval, self.update_playback_info)
            self.timer_slider_update.start()

    def update_playback_info(self):
        try:
            if self.main_window.is_closing:
                return

            if not self.player or not self.player.isPlaying():
                return

            self.player.update_last_known_position()

            position = 0
            if self.playback_info_program is not None \
                    and self.playback_info_program != self.player.get_program():
                program = self.playback_info_program
                percent = 100. if program.ut_start < self.player.get_program().ut_start else 0.
                self.ctrl_progress.setPercent(percent)
            else:
                percent, position = self.player.get_percent(True)
                self.ctrl_progress.setPercent(percent)
                if self.skip_secs + self.prev_skip_secs == 0:
                    self.ctrl_slider.setPercent(percent)
                program = self.player.get_program()

            self.ctrl_program_playtime.setLabel(format_secs(int(position)))
            self.ctrl_program_duration.setLabel(format_secs(program.length))
            self.ctrl_program_title.setLabel(program.title)
            self.ctrl_program_starttime.setLabel(format_date(program.ut_start, custom_format="%A, %d %b., %H:%M"))
            channel = self.api.channels[self.player.program.cid]
            self.ctrl_program_channel_icon.setImage(channel.get_icon())
            if self.getFocusId() != self.CTRL_SLIDER:
                self.preload_icon(self.ICON_PLAY, normalize(channel.name))
            self.defer_update_playback_info()
        except Exception, ex:
            self.preload_icon(self.ICON_ERROR, quote(ex.message.encode('utf-8')))
            log("Exception %s: message=%s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
