import os
import time
import logging

from services.dbcontroller import DbController
from services.qbittorrent_s import Qbittorent
from clients import anilibria_client, lostfilm_client
import domain.config as config

logger = logging.getLogger(__name__)
log_format = f'%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)


def main():
    logger.info('Reading config...')
    cfg = config.from_file(os.path.abspath('config.yaml'))

    logger.info('Init db...')
    db = DbController(cfg.qbittorrent.db_path, cfg.anilibria.db_path, cfg.lostfilm.db_path)

    while True:
        logger.info('Starting loop...')
        try:
            logger.info('Setup qbittorrent...')
            qbittorrent = Qbittorent(
                cfg.qbittorrent.host, cfg.qbittorrent.port,
                cfg.qbittorrent.username, cfg.qbittorrent.password
            )

            anilibria_codes = db.get_anilibria_codes()
            lostfilm_codes = db.get_lostfilm_codes()

            logger.info('Starting anilibria...')
            anilibria_series = anilibria_client.get_series(
                db, qbittorrent, cfg.qbittorrent.download_dir, cfg.anilibria.torrent_mirror,
                cfg.anilibria.api_mirror, anilibria_codes, cfg.base.proxy.as_dict
            )
            logger.info('Complete anilibria, update ' + str(len(anilibria_series)) + ' series')

            logger.info('Starting lostfilm...')
            lostfilm_series = lostfilm_client.get_series(
                db, qbittorrent, cfg.qbittorrent.download_dir, cfg.lostfilm.torrent_mirror,
                cfg.lostfilm.lf_session, lostfilm_codes, cfg.base.proxy.as_dict
            )
            logger.info('Complete lostfilm, update ' + str(len(lostfilm_series)) + ' series')

        except Exception as e:
            logger.exception(e)

        logger.info('Sleep for ' + str(cfg.base.sleep_interval) + ' minutes')
        time.sleep(cfg.base.sleep_interval * 60)


if __name__ == '__main__':
    main()
