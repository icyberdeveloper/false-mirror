import yaml
import time
import logging

from services.db_controller import DbController
from services.qbittorrent_s import Qbittorent
from clients import anilibria_client, lostfilm_client

logger = logging.getLogger(__name__)
log_format = f'%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)


def read_config(path):
    with open(path) as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    return cfg


def main():
    while True:

        logger.info('Starting loop...')
        logger.info('Reading config...')
        cfg = read_config('config.yaml')

        sleep_interval = cfg['global']['interval']
        db_path = cfg['global']['db_path']

        is_proxy_enabled = cfg['global']['proxy']['enabled']
        proxies = None
        if is_proxy_enabled:
            proxy_host = cfg['global']['proxy']['host']
            proxy_port = cfg['global']['proxy']['port']
            proxy_url = 'socks5://' + proxy_host + ':' + str(proxy_port)
            proxies = dict(http=proxy_url, https=proxy_url)

        qbittorrent_host = cfg['qbittorrent']['host']
        qbittorrent_port = cfg['qbittorrent']['port']
        qbittorrent_username = cfg['qbittorrent']['username']
        qbittorrent_password = cfg['qbittorrent']['password']
        qbittorrent_download_dir = cfg['qbittorrent']['download_dir']

        anilibria_torrent_mirror = cfg['anilibria']['torrent_mirrors'][0]
        anilibria_api_mirror = cfg['anilibria']['api_mirrors'][0]
        anilibria_series_names = cfg['anilibria']['series']

        lostfilm_torrent_mirror = cfg['lostfilm']['torrent_mirrors'][0]
        lostfilm_lf_session = cfg['lostfilm']['lf_session']
        lostfilm_series_names = cfg['lostfilm']['series']

        logger.info('Init db...')
        db = DbController(db_path)
        try:
            logger.info('Setup qbittorrent...')
            qbittorrent = Qbittorent(
                qbittorrent_host, qbittorrent_port,
                qbittorrent_username, qbittorrent_password
            )

            logger.info('Starting anilibria...')
            anilibria_series = anilibria_client.get_series(
                db, qbittorrent, qbittorrent_download_dir, anilibria_torrent_mirror,
                anilibria_api_mirror, anilibria_series_names, proxies
            )
            logger.info('Complete anilibria, update ' + str(len(anilibria_series)) + ' series')

            logger.info('Starting lostfilm...')
            lostfilm_series = lostfilm_client.get_series(
                db, qbittorrent, qbittorrent_download_dir, lostfilm_torrent_mirror,
                lostfilm_lf_session, lostfilm_series_names, proxies
            )
            logger.info('Complete lostfilm, update ' + str(len(lostfilm_series)) + ' series')

        except Exception as e:
            logger.exception(e)

        logger.info('Sleep for ' + str(sleep_interval) + ' minutes')
        time.sleep(sleep_interval * 60)


if __name__ == '__main__':
    main()
