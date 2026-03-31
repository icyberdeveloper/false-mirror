import requests
import logging
from retry import retry


logger = logging.getLogger(__name__)


@retry(requests.exceptions.ConnectionError, tries=5, delay=3, backoff=2, logger=logger)
def get(url, cookies=None, proxies=None):
    res = requests.get(url, cookies=cookies, proxies=proxies, timeout=30)
    if res.status_code != 200:
        raise requests.exceptions.RequestException(
            f'GET {url} returned status {res.status_code}'
        )
    return res
