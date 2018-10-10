import __builtin__
import os

setattr(__builtin__, 'addon_id', os.path.basename(os.path.abspath(os.path.dirname(__file__))))

import xbmcgui
from iptvlib import *
from iptvlib.mainwindow import MainWindow
from kartina import Kartina


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
        use_origin_icons = addon.getSetting("use_origin_icons") == 'true' or \
                           addon.getSetting("use_origin_icons") == True

        self.main_window.api = Kartina(
            hostname=hostname,
            use_origin_icons=use_origin_icons,
            username=username,
            password=password,
            working_path=xbmc.translatePath(addon.getAddonInfo("profile"))
        )

        return True


if __name__ == "__main__":
    Main()

