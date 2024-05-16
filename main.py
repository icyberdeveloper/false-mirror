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


DATABASE_FILENAME = '/storage/db.json'


def read_config(path):
    with open(path) as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    return cfg


def main(db_filename):
    while True:
        logger.info('Starting loop...')
        logger.info('Reading config...')
        cfg = read_config('config.yaml')

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
        db = TinyDB(db_filename)

        logger.info('Starting anilibria...')
        anilibria_series = anilibria_client.get_series(db, anilibria_torrent_mirror, anilibria_series_names)
        transmission.send_to_transmission(
           db, transmission_host, transmission_port,
           anilibria_download_dir, anilibria_series
        )

        logger.info('Starting lostfilm...')
        lostfilm_series = lostfilm_client.get_series(db, lostfilm_torrent_mirror, lostfilm_lf_session, lostfilm_series_names)
        transmission.send_to_transmission(
            db, transmission_host, transmission_port,
            lostfilm_download_dir, lostfilm_series
        )

        minutes = cfg['global']['interval']
        logger.info('Sleep for ' + minutes + ' minutes')
        time.sleep(minutes * 60)


if __name__ == '__main__':
    main(DATABASE_FILENAME)
