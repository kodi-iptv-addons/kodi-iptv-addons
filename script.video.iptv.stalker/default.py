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
import __builtin__
import os

setattr(__builtin__, 'addon_id', os.path.basename(os.path.abspath(os.path.dirname(__file__))))

import xbmcgui
from iptvlib import *
from iptvlib.mainwindow import MainWindow
from stalker import Stalker


class Main(object):
    def __init__(self):
        self.main_window = MainWindow.create(self.check_settings)
        self.main_window.doModal()
        del self.main_window

    def check_settings(self):
        # type: () -> bool
        username = addon.getSetting("username")
        password = addon.getSetting("password")
        if username == "" or password == "":
            dialog = xbmcgui.Dialog()
            yesno = bool(
                dialog.yesno(
                    addon.getAddonInfo("name"), " ",
                    get_string(TEXT_SUBSCRIPTION_REQUIRED_ID),
                    get_string(TEXT_SET_CREDENTIALS_ID)
                )
            )
            del dialog
            if yesno is True:
                addon.openSettings()
                return self.check_settings()
            else:
                return False

        hostname = addon.getSetting("hostname")
        adult = addon.getSetting("adult") == 'true' or \
                addon.getSetting("adult") == True
        timeshift = int(addon.getSetting("timeshift"))

        self.main_window.api = Stalker(
            hostname=hostname,
            adult=adult,
            timeshift=timeshift,
            username=username,
            password=password,
            working_path=xbmc.translatePath(addon.getAddonInfo("profile"))
        )

        return True


if __name__ == "__main__":
    Main()
