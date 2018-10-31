import os
import shutil
from datetime import datetime

from skinutils import DocumentCache, get_current_skin_path, get_local_skin_path, is_invalid_local_skin, \
    copy_skin_to_userdata, do_write_test, reload_skin, get_skin_name
from skinutils.fonts import FontManager as SkinUtilsFontManager


class FontManagerException(Exception):
    INSTALL_NEEDED = 1
    RESTART_NEEDED = 2
    INSTALL_NOT_NEEDED = 3


class FontManager(object, SkinUtilsFontManager):
    FONTS = {
        "script.module.iptvlib-font_MainMenu": "script.module.iptvlib-NotoSans-Bold.ttf",
        "script.module.iptvlib-font30_title": "script.module.iptvlib-NotoSans-Bold.ttf",
        "script.module.iptvlib-font30": "script.module.iptvlib-NotoSans-Regular.ttf",
        "script.module.iptvlib-font14": "script.module.iptvlib-NotoSans-Regular.ttf",
        "script.module.iptvlib-font12": "script.module.iptvlib-NotoSans-Regular.ttf",
    }
    script_path = None

    def __init__(self, script_path):
        self.__installed_names = []
        self.__installed_fonts = []
        self.__doc_cache = DocumentCache()
        self.script_path = script_path

    def check_fonts(self):
        if 'skin.estuary' == get_skin_name():
            raise FontManagerException(FontManagerException.INSTALL_NOT_NEEDED)

        if self.is_restart_needed():
            raise FontManagerException(FontManagerException.RESTART_NEEDED)

        if get_current_skin_path() != get_local_skin_path():
            if not self.is_writable():
                raise FontManagerException(FontManagerException.INSTALL_NOT_NEEDED)
            raise FontManagerException(FontManagerException.INSTALL_NEEDED)

        else:
            if not os.path.isdir(get_local_skin_path()):
                raise FontManagerException(FontManagerException.INSTALL_NEEDED)
            for f in self._list_skin_font_files():
                self.__doc_cache.add(f)
            self.install_fonts()

    def install_fonts(self):
        xml_path = os.path.join(self.script_path, "resources", "skins", "Default", "720p", "font.xml")
        font_dir = os.path.join(self.script_path, "resources", "skins", "Default", "fonts")
        self.install_file(xml_path, font_dir)
        reload_skin()

    @staticmethod
    def install_skin():
        copy_skin_to_userdata(ask_user=False)

    @staticmethod
    def is_writable():
        # type: () -> bool
        skin_path = get_local_skin_path()
        return not os.access(skin_path, os.W_OK) or not do_write_test(skin_path)

    @staticmethod
    def is_restart_needed():
        # type: () -> bool
        current_skin_path = get_current_skin_path()
        local_skin_path = get_local_skin_path()

        if os.path.isdir(local_skin_path) and current_skin_path != local_skin_path:
            if is_invalid_local_skin():
                time_suffix = datetime.now().strftime('%Y%m%d%H%M%S')
                shutil.move(local_skin_path, local_skin_path + '-skinutils-' + time_suffix)
                copy_skin_to_userdata(ask_user=False)
            return True
        return False
