import requests
import logging
from retry import retry


logger = logging.getLogger(__name__)


@retry(Exception, tries=10, delay=5, backoff=2, logger=logger)
def get(url, cookies=None, proxies=None):
    try:
        res = requests.get(url, cookies=cookies, proxies=proxies)
        if res.status_code != 200:
            raise requests.exceptions.RequestException(
                'GET request return status_code = {}, with url {}'.format(res.status_code, url)
            )
        return res
    except requests.exceptions.RequestException as e:
        logger.error('GET Request failed with url: {}'.format(url))
        raise e
