import base64
import network
import logging
import transmissionrpc
from retry import retry


logger = logging.getLogger(__name__)


class Transmission:
    def __init__(self, host, port):
        logger.info('Setup transmission...')
        self.transmission = transmissionrpc.Client(address=host, port=port)

    @retry(Exception, tries=10, delay=5, backoff=2, logger=logger)
    def send_to_transmission(self, filtered_series, download_dir, proxies):
        logger.info('Start processing {} series for {}'.format(len(filtered_series), download_dir))

        for series in filtered_series:
            logger.info('Process torrent: {}'.format(series.torrent_url))
            response = network.get(series.torrent_url, proxies=proxies)
            b64 = base64.b64encode(response.content).decode('utf-8')

            res = self.transmission.add_torrent(b64, download_dir=download_dir)
            logger.info('Add new series: ' + series.name + ', with url: ' + series.torrent_url)
