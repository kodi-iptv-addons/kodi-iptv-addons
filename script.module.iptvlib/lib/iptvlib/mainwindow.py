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
from iptvlib.fonts import FontManager, FontManagerException
from iptvlib.tvdialog import TvDialog


class MainWindow(xbmcgui.WindowXML, WindowMixin):
    SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__) + u'/../../')

    check_settings_handler = None  # type: callable()
    api = None  # type: Api
    tv_dialog = None  # type: TvDialog
    tv_dialog_xml_file = "tv_dialog_font.xml"
    fm = None  # type: FontManager

    _initialized = False  # type: bool

    def __init__(self, *args, **kwargs):
        self.fm = FontManager(MainWindow.SCRIPT_PATH)
        self.check_skin()

        if kwargs.has_key("check_settings_handler"):
            self.check_settings_handler = kwargs.pop("check_settings_handler", None)
        super(MainWindow, self).__init__(**kwargs)

    def check_skin(self):
        try:
            self.fm.check_fonts()
        except FontManagerException, ex:
            if ex.message == FontManagerException.INSTALL_NEEDED:
                xbmcgui.Dialog().ok(
                    addon.getAddonInfo("name"), " ",
                    get_string(TEXT_INSTALL_EXTRA_RESOURCES_ID)
                )
                self.fm.install_skin()
                self.close()
                sys.exit()
            elif ex.message == FontManagerException.RESTART_NEEDED:
                xbmcgui.Dialog().ok(
                    addon.getAddonInfo("name"), " ",
                    get_string(TEXT_PLEASE_RESTART_KODI_ID)
                )
                self.close()
                sys.exit()
            elif ex.message == FontManagerException.INSTALL_NOT_NEEDED:
                self.tv_dialog_xml_file = "tv_dialog.xml"

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

        self.tv_dialog = TvDialog(self.tv_dialog_xml_file, MainWindow.SCRIPT_PATH, 'Default', '720p', main_window=self)
        self.tv_dialog.doModal()
        del self.tv_dialog

    def close(self):
        self.is_closing = True
        try:
            if self.tv_dialog:
                self.tv_dialog.close()
            del self.api
        except Exception, ex:
            log("Exception %s: message=%s" % (type(ex), ex.message))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
        super(MainWindow, self).close()

    def check_settings(self):
        if callable(self.check_settings_handler) is False or self.check_settings_handler() is False:
            return False

        try:
            self.api.login()
        except ApiException, ex:
            log("Exception %s: message=%s, code=%s" % (type(ex), ex.message, ex.code))
            log(traceback.format_exc(), xbmc.LOGDEBUG)
            dialog = xbmcgui.Dialog()
            if ex.code == Api.E_API_ERROR:
                if dialog.yesno(
                        addon.getAddonInfo("name"),
                        get_string(TEXT_AUTHENTICATION_FAILED_ID) + ":",
                        ex.message,
                        get_string(TEXT_CHECK_SETTINGS_ID)):
                    addon.openSettings()
                    return self.check_settings()
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
            return False

        return True
