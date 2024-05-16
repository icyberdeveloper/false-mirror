import base64
import requests
import logging
import transmissionrpc


logger = logging.getLogger(__name__)


def send_to_transmission(db, host, port, download_dir, filtered_series):
    logger.info('Setup transmission...')
    transmission = transmissionrpc.Client(address=host, port=port)

    logger.info('Start processing {} series for {}'.format(len(filtered_series), download_dir))

    for series in filtered_series:
        logger.info('Process torrent: {}'.format(series.torrent_url))
        response = requests.get(series.torrent_url)
        b64 = base64.b64encode(response.content).decode('utf-8')

        res = transmission.add_torrent(b64, download_dir=download_dir)
        db.insert({'name': series.name, 'url': series.torrent_url})
        logger.info('Add new series: ' + series.name + ', with url: ' + series.torrent_url)