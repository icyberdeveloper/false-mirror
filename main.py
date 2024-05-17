import yaml
import time
import logging
from tinydb import TinyDB

import lostfilm_client
import transmission
import anilibria_client


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

        transmission_host = cfg['transmission']['host']
        transmission_port = cfg['transmission']['port']

        anilibria_torrent_mirror = cfg['anilibria']['torrent_mirrors'][0]
        anilibria_series_names = cfg['anilibria']['series']
        anilibria_download_dir = cfg['anilibria']['path']

        lostfilm_torrent_mirror = cfg['lostfilm']['torrent_mirrors'][0]
        lostfilm_lf_session = cfg['lostfilm']['lf_session']
        lostfilm_series_names = cfg['lostfilm']['series']
        lostfilm_download_dir = cfg['lostfilm']['path']

        logger.info('Init db...')
        db = TinyDB(db_path)
        try:
            # logger.info('Starting anilibria...')
            # anilibria_series = anilibria_client.get_series(db, anilibria_torrent_mirror, anilibria_series_names, proxies)
            # transmission.send_to_transmission(
            #    db, transmission_host, transmission_port,
            #    anilibria_download_dir, anilibria_series
            # )

            logger.info('Starting lostfilm...')
            lostfilm_series = lostfilm_client.get_series(
                db, lostfilm_torrent_mirror, lostfilm_lf_session, lostfilm_series_names, proxies
            )
            transmission.send_to_transmission(
                db, transmission_host, transmission_port,
                lostfilm_download_dir, lostfilm_series
            )
        except Exception as e:
            logger.error(e)

        logger.info('Sleep for ' + str(sleep_interval) + ' minutes')
        time.sleep(sleep_interval * 60)


if __name__ == '__main__':
    main()
