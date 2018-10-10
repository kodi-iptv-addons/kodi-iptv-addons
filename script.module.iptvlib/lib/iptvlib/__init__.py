# coding=utf-8
import __builtin__
import calendar
import datetime
import httplib
import math
import os
import platform
import threading
import time
from Queue import Queue
from functools import wraps
from httplib import HTTPResponse
from urlparse import urlparse

import xbmc
import xbmcaddon

if hasattr(__builtin__, 'addon_id') is False:
    setattr(__builtin__, 'addon_id', os.path.basename(os.path.abspath(os.path.dirname(__file__))))

addon = xbmcaddon.Addon(id=getattr(__builtin__, 'addon_id'))

utc_local_offset = math.ceil(calendar.timegm(time.localtime()) - time.time())

TENSECS = 10  # type: int
MIN = 60  # type: int
HALFHOUR = 1800  # type: int
HOUR = 3600  # type: int
DAY = 86400  # type: int
TREEDAYS = 259200  # type: int
WEEK = 604800  # type: int
TWOWEEKS = 1209600  # type: int

TEXT_SUBSCRIPTION_REQUIRED_ID = 30101  # type: int
TEXT_SET_CREDENTIALS_ID = 30102  # type: int
TEXT_AUTHENTICATION_FAILED_ID = 30103  # type: int
TEXT_CHECK_CREDENTIALS_ID = 30104  # type: int
TEXT_NOT_PLAYABLE_ID = 30105  # type: int
TEXT_SERVICE_ERROR_OCCURRED_ID = 30106  # type: int
TEXT_SURE_TO_EXIT_ID = 30107  # type: int
TEXT_ARCHIVE_NOT_AVAILABLE_YET_ID = 30108  # type: int
TEXT_WANNA_JUMP_TO_ARCHIVE_ID = 30109  # type: int
TEXT_CHANNEL_HAS_NO_ARCHIVE_ID = 30110  # type: int
TEXT_LIVE_NO_FORWARD_SKIP_ID = 30111  # type: int
TEXT_IMPLEMENTATION_ERROR_ID = 30112  # type: int
TEXT_NO_API_INSTANCE_PROVIDED_ID = 30113  # type: int
TEXT_PLAYLIST_INFO_REQUIRED_ID = 30114  # type: int
TEXT_PLAYLIST_PROVIDE_PATH_ID = 30115  # type: int
TEXT_NO_INFO_AVAILABLE_ID = 30201  # type: int
TEXT_ABBR_MINUTES_ID = 30202  # type: int
TEXT_ABBR_SECONDS_ID = 30203  # type: int
TEXT_LOADING_EPG_ID = 30204  # type: int
TEXT_CHECK_XMLTV_URL_ID = 30205  # type: int
TEXT_PARSE_XMLTV_ID = 30206  # type: int
TEXT_CACHE_XMLTV_ID = 30207  # type: int
TEXT_LOAD_XMLTV_FROM_CACHE_ID = 30208  # type: int
TEXT_DOWNLOAD_XMLTV_ID = 30209  # type: int


# noinspection PyUnresolvedReferences
class WindowMixin(object):
    is_closing = False  # type: bool

    def __init__(self, **kwargs):
        self.is_closing = False
        super(WindowMixin, self).__init__()

    def close(self):
        self.is_closing = True
        super(WindowMixin, self).close()

    def show_control(self, *control_ids):
        for control_id in control_ids:
            control = self.getControl(control_id)
            if control:
                control.setVisible(True)

    def hide_control(self, *control_ids):
        for control_id in control_ids:
            control = self.getControl(control_id)
            if control:
                control.setVisible(False)

    def set_control_image(self, control_id, image):
        control = self.getControl(control_id)
        if control:
            control.setImage(image.encode('utf-8'))

    def setcontrol_label(self, control_id, label):
        control = self.getControl(control_id)
        if control and label:
            control.setLabel(label)

    def set_control_text(self, control_id, text):
        control = self.getControl(control_id)
        if control:
            control.setText(text)


def get_string(id):
    return xbmcaddon.Addon('script.module.iptvlib').getLocalizedString(id).encode('utf-8')


def show_small_popup(title='', msg='', delay=5000, image=''):
    xbmc.executebuiltin('XBMC.Notification("%s","%s",%d,"%s")' % (title, msg, delay, image))


def build_user_agent():
    # type: () -> str
    return 'KODI/%s (%s; %s %s; python %s) %s/%s ' % (
        xbmc.getInfoLabel('System.BuildVersion').split(" ")[0],
        xbmc.getInfoLabel('System.BuildVersion'),
        platform.system(),
        platform.release(),
        platform.python_version(),
        addon.getAddonInfo('id').replace('-DEV', ''),
        addon.getAddonInfo('version')
    )


def xor(s, t):
    # type: (str, str) -> str
    t = (t * ((len(s) / len(t)) + 1))[:len(s)]
    if isinstance(s, str):
        return "".join(chr(ord(a) ^ ord(b)) for a, b in zip(s, t))
    else:
        return bytes([a ^ b for a, b in zip(s, t)])


def secs_to_percent(length, played):
    # type: (int, float) -> float
    return (100 * played) / length


def percent_to_secs(length, percent):
    # type: (int, float) -> int
    return int((length * percent) / 100)


def format_secs(secs, id="time"):
    # type: (int, str) -> str
    if id == "time":
        return "{:0>8}".format(datetime.timedelta(seconds=secs))
    if id == "skip":
        prefix = "+"
        if secs < 0:
            prefix = "-"
            secs *= -1
        elif secs == 0:
            prefix = ""
        if secs > 60:
            return "%s%s %s" % (prefix, secs / 60, get_string(TEXT_ABBR_MINUTES_ID))
        return "%s%s %s" % (prefix, secs, get_string(TEXT_ABBR_SECONDS_ID))


def format_date(timestamp, id="dateshort", custom_format=None):
    # type: (float, str, str) -> str
    if timestamp:
        if custom_format is not None:
            return datetime.datetime.fromtimestamp(timestamp).strftime(custom_format)
        fmt = xbmc.getRegion(id)
        return datetime.datetime.fromtimestamp(timestamp).strftime(fmt)
    return ''


def time_now():
    # type: () -> float
    return time.time()


def str_to_datetime(str_date, fmt):
    # type: (str, str) -> datetime.datetime
    try:
        d = datetime.datetime.strptime(str_date, fmt)
    except TypeError:
        from time import strptime
        d = datetime.datetime(*(strptime(str_date, fmt)[0:6]))
    return d


def str_to_timestamp(str_date, fmt):
    # type: (str, str) -> int
    try:
        return int(time.mktime(str_to_datetime(str_date, fmt).timetuple()))
    except:
        return 0


def run_async(func):
    """
    Decorator to run a function in a separate thread
    """

    @wraps(func)
    def async_func(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return async_func


def do_download(q, results):
    # type: (Queue, dict[str, dict]) -> None
    while True:
        url = q.get()
        print "download %s" % url
        purl = urlparse(url)
        conn = httplib.HTTPConnection(purl.netloc)
        conn.request("GET", url)
        results[url] = conn.getresponse()
        q.task_done()


def download(urls):
    # type: (list) -> dict[str, HTTPResponse]
    num_threads = len(urls)
    queue = Queue()
    results = dict()

    for i in range(num_threads):
        thread = threading.Thread(target=do_download, args=(queue, results,))
        thread.setDaemon(True)
        thread.start()

    for url in urls:
        queue.put(url)
    queue.join()

    while queue.unfinished_tasks > 0:
        continue

    return results


def log(msg, level=xbmc.LOGNOTICE):
    xbmc.log('%s: %s' % (addon.getAddonInfo('name'), msg), level)


def normalize(text):
    # type: (str) -> str
    if type(text) is not unicode:
        text = unicode(text)
    symbols = (u"абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
               u"abvgdeejzijklmnoprstufhzcss_y_euaABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUA")
    tr = dict([(ord(a), ord(b)) for (a, b) in zip(*symbols)])
    import re
    regs = [
        '\s+\+[0-9]+',  # time shift suffix, e.g. "RTL +7"
        '\s+\[[a-zA-Z]+\]',  # land code suffix, e.g. "RTL [de]"
        '\s+(HQ)',  # High quality suffix, e.g. "RTL (HQ)"
    ]
    for reg in regs:
        text = re.sub(reg, '', text)
    return re.sub('[^0-9a-zA-Z+-]+', '', text.translate(tr)).upper()


x = lambda s: str.decode(s, "hex")
z = lambda s: str.encode(s, "hex")
h1 = '3d37612b5542244c4e3952775a3f6b5a24367732426e583750'
h2 = '5543155b26780b63394e25593d50043d48535a532c0f344e24' \
     '54541205362d49632d563e1b3f5c1f65505f130f172f750e66' \
     '0b03541f6571097f684f6f467c4b563f52531946640b3b0a2b' \
     '4011044a6839596a2b556f0c27190e2c194d0a1421073c0a2b' \
     '40113e162e3f'
