from qbittorrent import Client
import logging
from retry import retry
from services import network


logger = logging.getLogger(__name__)


class Qbittorent:
    def __init__(self, host, port, username, password):
        self.qb_client = Client('http://' + host + ':' + str(port) + '/')
        self.qb_client.login(username=username, password=password)

    @retry(Exception, tries=10, delay=5, backoff=2, logger=logger)
    def send_to_qbittorent(self, filtered_series, proxies):
        for series in filtered_series:
            logger.info('Process torrent: {}'.format(series.torrent_url))
            torrent_bites = network.get(series.torrent_url, proxies=proxies)

            res = self.qb_client.download_from_file(torrent_bites.content, save_path=series.download_path)
            logger.info('Add new series: ' + series.name + ', with url: ' + series.torrent_url)
