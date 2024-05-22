import os
import time
import logging

from services.dbcontroller import DbController
from services.qbittorrent_s import Qbittorent
from services.renamer import Renamer
from clients import anilibria_client, lostfilm_client
import domain.config as config

logger = logging.getLogger(__name__)
log_format = f'%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)


def process_anilibria_series(db, qbittorrent, download_dir, torrent_mirror, api_mirror, proxies):
    try:
        logger.info('Starting anilibria...')
        anilibria_codes = db.get_anilibria_codes()
        anilibria_series = anilibria_client.get_series(
            db, qbittorrent, download_dir, torrent_mirror,
            api_mirror, anilibria_codes, proxies
        )
        logger.info('Complete anilibria, update ' + str(len(anilibria_series)) + ' series')
    except Exception as e:
        logger.error('Unable to complete anilibria series: ' + str(e))
        raise e


def process_lostfilm_series(db, qbittorrent, download_dir, torrent_mirror, lf_session, proxies):
    try:
        logger.info('Starting lostfilm...')
        lostfilm_codes = db.get_lostfilm_codes()
        lostfilm_series = lostfilm_client.get_series(
            db, qbittorrent, download_dir, torrent_mirror,
            lf_session, lostfilm_codes, proxies
        )
        logger.info('Complete lostfilm, update ' + str(len(lostfilm_series)) + ' series')
    except Exception as e:
        logger.error('Unable to complete lostfilm series: ' + str(e))
        raise e


def main():
    logger.info('Reading config...')
    cfg = config.from_file(os.path.abspath('config.yaml'))

    logger.info('Init db...')
    db = DbController(cfg.qbittorrent.db_path, cfg.anilibria.db_path, cfg.lostfilm.db_path)

    logger.info('Init renamer...')
    renamer = Renamer(cfg.renamer.root_dir, cfg.renamer.anilibria.regex)

    while True:
        logger.info('Starting loop...')
        try:
            logger.info('Setup qbittorrent...')
            qbittorrent = Qbittorent(
                cfg.qbittorrent.host, cfg.qbittorrent.port,
                cfg.qbittorrent.username, cfg.qbittorrent.password
            )

            process_anilibria_series(
                db, qbittorrent, cfg.qbittorrent.download_dir, cfg.anilibria.torrent_mirror,
                cfg.anilibria.api_mirror, cfg.base.proxy.as_dict
            )
            process_lostfilm_series(
                db, qbittorrent, cfg.qbittorrent.download_dir, cfg.lostfilm.torrent_mirror,
                cfg.lostfilm.lf_session, cfg.base.proxy.as_dict
            )

            logger.info('Starting renamer...')
            renamer.rename()

        except Exception as e:
            logger.exception(e)

        logger.info('Sleep for ' + str(cfg.base.sleep_interval) + ' minutes')
        time.sleep(cfg.base.sleep_interval * 60)


if __name__ == '__main__':
    main()
