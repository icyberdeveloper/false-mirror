import socket
import ssl
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.connection import HTTPSConnection
from retry import retry


logger = logging.getLogger(__name__)


class ServerError(requests.exceptions.RequestException):
    """Retryable server-side error (5xx)."""
    pass


class _DeviceBoundHTTPSConnection(HTTPSConnection):
    """HTTPS connection bound to a specific network interface."""

    _bind_device = None

    def connect(self):
        sock = socket.create_connection(
            (self._dns_host, self.port),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self._bind_device.encode())
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self._dns_host)


class _DeviceBoundHTTPSPool(HTTPSConnectionPool):
    _bind_device = None

    def _new_conn(self):
        conn = _DeviceBoundHTTPSConnection(host=self.host, port=self.port)
        conn._bind_device = self._bind_device
        conn.timeout = self.timeout.connect_timeout
        return conn


class DeviceBoundAdapter(HTTPAdapter):
    """Requests adapter that binds connections to a specific network interface."""

    def __init__(self, device, **kwargs):
        self._device = device
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        pool_cls = type('BoundPool', (_DeviceBoundHTTPSPool,), {'_bind_device': self._device})
        self.poolmanager.pool_classes_by_scheme = {
            'https': pool_cls,
        }


@retry((requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError, ServerError), tries=5, delay=3, backoff=2, logger=logger)
def get(url, cookies=None, proxies=None, bind_device=None):
    if bind_device:
        session = requests.Session()
        session.mount('https://', DeviceBoundAdapter(bind_device))
        res = session.get(url, cookies=cookies, timeout=30)
    else:
        res = requests.get(url, cookies=cookies, proxies=proxies, timeout=30)
    if res.status_code >= 500:
        raise ServerError(f'GET {url} returned status {res.status_code}')
    if res.status_code != 200:
        raise requests.exceptions.RequestException(
            f'GET {url} returned status {res.status_code}'
        )
    return res
