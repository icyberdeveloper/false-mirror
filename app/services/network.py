import requests
import logging
from retry import retry


logger = logging.getLogger(__name__)


class ServerError(requests.exceptions.RequestException):
    """Retryable server-side error (5xx)."""
    pass


@retry((requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError, ServerError), tries=5, delay=3, backoff=2, logger=logger)
def get(url, cookies=None, proxies=None):
    res = requests.get(url, cookies=cookies, proxies=proxies, timeout=30)
    if res.status_code >= 500:
        raise ServerError(f'GET {url} returned status {res.status_code}')
    if res.status_code != 200:
        raise requests.exceptions.RequestException(
            f'GET {url} returned status {res.status_code}'
        )
    return res
