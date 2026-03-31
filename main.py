import os
import time
import logging

from domain.config import from_file
from services.database import Database
from services.library import Library
from services.qbittorrent import QBittorrent
from services.renamer import Renamer
from services.tracker import Tracker
from clients import anilibria, lostfilm


logger = logging.getLogger(__name__)
log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)


def wait_for_qbittorrent(host, port, timeout=120):
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError:
            logger.info(f'Waiting for qBittorrent at {host}:{port}...')
            time.sleep(5)
    return False


def main():
    logger.info('Reading config...')
    cfg = from_file(os.path.abspath('config.yaml'))

    logger.info('Init database...')
    db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)

    library = Library(
        library_dir=cfg.renamer.root_dir + '/TV Shows',
        incomplete_dir=cfg.qbittorrent.incomplete_dir,
    )
    renamer = Renamer(cfg.renamer.root_dir, cfg.renamer.anilibria_regex)
    tracker = Tracker(
        db_path='/storage/tracker.json',
        tg_token=cfg.nocron.token,
        tg_chat_id=os.environ.get('HEALTHCHECK_TG_CHAT_ID', '197650166'),
    )
    proxies = cfg.proxy.as_dict

    logger.info('Waiting for qBittorrent...')
    wait_for_qbittorrent(cfg.qbittorrent.host, cfg.qbittorrent.port)

    while True:
        logger.info('=== Starting cycle ===')
        try:
            qbt = QBittorrent(
                cfg.qbittorrent.host, cfg.qbittorrent.port,
                cfg.qbittorrent.username, cfg.qbittorrent.password,
            )

            # Anilibria
            try:
                codes = db.get_anilibria_codes()
                added = anilibria.get_series(
                    library, qbt, cfg.qbittorrent.download_dir,
                    cfg.anilibria.torrent_mirror, cfg.anilibria.api_mirror,
                    codes, proxies, tracker=tracker,
                )
                logger.info(f'Anilibria: added {len(added)} new episodes')
            except Exception as e:
                logger.error(f'Anilibria failed: {e}')

            # LostFilm
            try:
                codes = db.get_lostfilm_codes()
                added = lostfilm.get_series(
                    library, qbt, cfg.qbittorrent.download_dir,
                    cfg.lostfilm.torrent_mirror, cfg.lostfilm.lf_session,
                    codes, proxies, tracker=tracker,
                )
                logger.info(f'LostFilm: added {len(added)} new episodes')
            except Exception as e:
                logger.error(f'LostFilm failed: {e}')

            # Renamer
            try:
                renamer.rename()
            except Exception as e:
                logger.error(f'Renamer failed: {e}')

            # Post-download verification
            try:
                tracker.check(qbt.client, cfg.renamer.root_dir + '/TV Shows')
            except Exception as e:
                logger.error(f'Tracker failed: {e}')

        except Exception as e:
            logger.exception(f'Cycle error: {e}')

        logger.info(f'Sleeping {cfg.sleep_interval} minutes...')
        time.sleep(cfg.sleep_interval * 60)


if __name__ == '__main__':
    main()
