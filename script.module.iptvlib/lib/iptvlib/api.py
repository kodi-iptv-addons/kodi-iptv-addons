# coding=utf-8
import abc
import json
import os
import urllib2
from collections import OrderedDict
from urllib import urlencode

from iptvlib import build_user_agent, log
from iptvlib.models import Group, Program, Channel


class ApiException(Exception):
    def __init__(self, message, code, origin_error=None):
        self.message = message
        self.code = code
        self.origin_error = origin_error

    def __repr__(self):
        return "ApiException: (%s) %s" % (self.code, self.message)


class Api:
    __metaclass__ = abc.ABCMeta

    AUTH_STATUS_NONE = 0
    AUTH_STATUS_OK = 1
    AUTH_MAX_ATTEMPTS = 3

    E_UNKNOW_ERROR = 1000
    E_HTTP_REQUEST_FAILED = 1001
    E_JSON_DECODE = 1002
    E_AUTH_ERROR = 1003

    auth_status = AUTH_STATUS_NONE  # type: int
    username = None  # type: str
    password = None  # type: str
    working_path = None  # type: str
    cookie_file = None  # type: str
    settings_file = None  # type: str
    _last_error = None  # type: dict
    _attempt = 0  # type: int
    _groups = None  # type: OrderedDict[str, Group]
    _channels = None  # type: OrderedDict[str, Channel]

    def __init__(self, username=None, password=None, working_path="./"):
        self.auth_status = self.AUTH_STATUS_NONE
        self.username = username
        self.password = password
        self.working_path = working_path
        if not os.path.exists(self.working_path):
            os.makedirs(self.working_path)
        self.cookie_file = os.path.join(self.working_path, "%s.cookie.txt" % self.__class__.__name__)
        self.settings_file = os.path.join(self.working_path, "%s.settings.txt" % self.__class__.__name__)
        self._last_error = None
        self._groups = OrderedDict()
        self._channels = OrderedDict()

    @property
    def client_id(self):
        return "%s:%s" % (self.__class__.__name__, self.username)

    @property
    def user_agent(self):
        # type: () -> str
        """
        User agent of HTTP client.
        :rtype: str
        """
        return build_user_agent()

    @property
    def groups(self):
        if len(self._groups) == 0:
            self._groups = self.get_groups()
            self._channels = OrderedDict()
            for group in self._groups.values():
                self._channels.update(group.channels)
        return self._groups

    @property
    def channels(self):
        if len(self._channels) == 0:
            len(self.groups)
        return self._channels

    @abc.abstractproperty
    def base_api_url(self):
        # type: () -> str
        """
        Base URL of API.
        :rtype: str
        """
        return ""

    @abc.abstractproperty
    def base_icon_url(self):
        # type: () -> str
        """
        Base URL of channel icons.
        :rtype: str
        """
        return ""

    @abc.abstractproperty
    def host(self):
        # type: () -> str
        """
        Api hostname.
        :rtype: str
        """
        return ""

    @abc.abstractproperty
    def diff_live_archive(self):
        # type: () -> int
        """
        Difference between live stream and archive stream in seconds.
        :rtype: int
        """
        return -1

    @abc.abstractproperty
    def archive_ttl(self):
        # type: () -> int
        """
        Time to live (ttl) of archive streams in seconds.
        :rtype: int
        """
        return -1

    @abc.abstractmethod
    def login(self):
        # type: () -> dict
        """Login to the IPTV service"""
        pass

    @abc.abstractmethod
    def is_login_uri(self, uri):
        # type: (str) -> bool
        """
        Checks whether given URI is used for login
        :rtype: str
        """
        pass

    @abc.abstractmethod
    def get_groups(self):
        # type: () ->  OrderedDict[str, Group]
        """
        Returns the groups from the service
        :rtype: dict[str, Group]
        """
        pass

    @abc.abstractmethod
    def get_stream_url(self, cid, ut_start=None):
        # type: (str, int) -> str
        """
        Returns the stream URL for given channel id and timestamp
        :rtype: str
        """
        pass

    @abc.abstractmethod
    def get_epg(self, channel):
        # type: (Channel) -> dict[int, Program]
        """
        Returns the EPG for given channel id
        :rtype: dict[int, Program]
        """
        pass

    @abc.abstractmethod
    def get_cookie(self):
        # type: () -> str
        """
        Returns cookie
        :rtype: str
        """
        pass

    def read_cookie_file(self):
        # type: () -> str
        """
        Returns cookie stored in the cookie file
        :rtype: str
        """
        cookie = ""
        if os.path.isfile(self.cookie_file):
            with open(self.cookie_file, 'r') as fh:
                cookie = fh.read()
                fh.close()
        return cookie

    def write_cookie_file(self, data):
        # type: (str) -> None
        """
        Stores cookie to the cookie file
        :rtype: None
        """
        with open(self.cookie_file, 'w') as fh:
            fh.write(data)
            fh.close()

    def read_settings_file(self):
        # type: () -> dict
        """
        Returns settings stored in the settings file
        :rtype: dict
        """
        settings = None
        if os.path.isfile(self.settings_file):
            with open(self.settings_file, 'r') as fh:
                json_string = fh.read()
                fh.close()
                settings = json.loads(json_string)
        return settings

    def write_settings_file(self, data):
        # type: (dict) -> None
        """
        Stores settings to the settings file
        :rtype: None
        """
        with open(self.settings_file, 'w') as fh:
            fh.write(json.dumps(data))
            fh.close()

    def make_request(self, uri, payload=None, method="GET", headers=None):
        # type: (str, dict, str, dict) -> dict
        """
        Makes HTTP request to the IPTV API
        :param uri: URL of the IPTV API
        :param payload: Payload data
        :param method: HTTP method
        :param headers: Additional HTTP headers
        :return:
        """
        headers = headers or {}
        if self.auth_status != self.AUTH_STATUS_OK and not self.is_login_uri(uri):
            self.login()
            return self.make_request(uri, payload, method)

        self._last_error = None
        url = self.base_api_url % uri
        headers["User-Agent"] = self.user_agent
        headers["Connection"] = "Close"

        cookie = self.get_cookie()
        if cookie != "" and not self.is_login_uri(uri):
            headers["Cookie"] = cookie

        data = None
        if payload:
            if method == "POST":
                data = urlencode(payload)
            elif method == "GET":
                url += "?%s" % urlencode(payload)
        req = urllib2.Request(url=url, headers=headers, data=data)

        json_data = ""
        try:
            json_data = urllib2.urlopen(req).read()
            response = json.loads(json_data)
        except urllib2.URLError, ex:
            response = {
                "error": {
                    "message": str(ex),
                    "code": self.E_HTTP_REQUEST_FAILED,
                    "details": {
                        "url": url,
                        "data": data,
                        "headers": headers
                    }
                }
            }
            pass
        except ValueError, ex:
            response = {
                "error": {
                    "message": "Unable decode server response: %s" % str(ex),
                    "code": self.E_JSON_DECODE,
                    "details": {
                        "response": json_data
                    }
                }
            }
            pass
        except Exception, ex:
            response = {
                "error": {
                    "message": "%s: %s" % (type(ex), str(ex)),
                    "code": self.E_UNKNOW_ERROR
                }
            }
            pass

        if "error" in response:

            self._last_error = response

            if self.is_login_uri(uri):
                self.auth_status = self.AUTH_STATUS_NONE
                try:
                    os.remove(self.cookie_file)
                except OSError:
                    pass
                self._attempt += 1
                if self._attempt < self.AUTH_MAX_ATTEMPTS:
                    return self.make_request(uri, payload, method)
                else:
                    self._attempt = 0
                raise ApiException(self._last_error["message"], self._last_error["code"])
            else:
                raise ApiException(self._last_error["message"], self._last_error["code"])

        return response
