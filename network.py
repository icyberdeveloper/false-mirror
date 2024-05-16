import requests
import logging


logger = logging.getLogger(__name__)


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
        return None
