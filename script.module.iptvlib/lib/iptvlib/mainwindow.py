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

import xbmcgui
from iptvlib import *
from iptvlib.api import Api, ApiException
from iptvlib.tvdialog import TvDialog


class MainWindow(xbmcgui.WindowXML, WindowMixin):
    SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__) + u'/../../')
    check_settings_handler = None  # type: callable()
    api = None  # type: Api
    tv_dialog = None  # type: TvDialog

    _initialized = False  # type: bool

    def __init__(self, *args, **kwargs):
        if kwargs.has_key("check_settings_handler"):
            self.check_settings_handler = kwargs.pop("check_settings_handler", None)
        super(MainWindow, self).__init__(**kwargs)

    @classmethod
    def create(cls, check_settings_handler):
        return cls("main_window.xml", MainWindow.SCRIPT_PATH, 'Default', '720p',
                   check_settings_handler=check_settings_handler)

    def onInit(self):
        if self._initialized is True:
            return

        if self.check_settings() is False:
            self.close()
            return

        self._initialized = True

        self.tv_dialog = TvDialog("tv_dialog.xml", MainWindow.SCRIPT_PATH, 'Default', '720p', main_window=self)
        self.tv_dialog.doModal()
        del self.tv_dialog

    def close(self):
        self.is_closing = True
        try:
            if self.tv_dialog:
                self.tv_dialog.close()
            del self.api
        except Exception, ex:
            log("Exception %s: %s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
        super(MainWindow, self).close()

    def check_settings(self):
        if callable(self.check_settings_handler) is False or self.check_settings_handler() is False:
            return False

        try:
            self.api.login()
        except ApiException, ex:
            dialog = xbmcgui.Dialog()
            if dialog.yesno(
                    addon.getAddonInfo("name"),
                    get_string(TEXT_AUTHENTICATION_FAILED_ID),
                    ex.message,
                    get_string(TEXT_CHECK_SETTINGS_ID)):
                addon.openSettings()
                return self.check_settings()
            return False

        return True
