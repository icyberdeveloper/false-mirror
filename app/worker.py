"""
Isolated per-series workers. Each function processes one show independently.
Safe to call from bot (immediate) or scheduler (periodic).
"""
import logging

import os

from config import from_file
from services.database import Database
from services.library import Library
from services.qbittorrent import QBittorrent
from services.tracker import Tracker
from clients import anilibria, lostfilm

logger = logging.getLogger(__name__)


def _load_env():
    """Load shared config and services. Cheap to call — just reads config + connects."""
    cfg = from_file(os.path.abspath('config.yaml'))
    db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)
    library = Library(
        library_dir=cfg.renamer.root_dir + '/TV Shows',
        incomplete_dir=cfg.qbittorrent.incomplete_dir,
    )
    tracker = Tracker(
        db_path='/storage/tracker.json',
        tg_token=cfg.nocron.token,
        tg_chat_id=os.environ.get('HEALTHCHECK_TG_CHAT_ID', '197650166'),
    )
    qbt = QBittorrent(
        cfg.qbittorrent.host, cfg.qbittorrent.port,
        cfg.qbittorrent.username, cfg.qbittorrent.password,
    )
    return cfg, db, library, tracker, qbt


def check_lostfilm_show(code):
    """Check one LostFilm show for new episodes. Fully isolated."""
    try:
        cfg, db, library, tracker, qbt = _load_env()
        codes = [{'code': code}]
        added = lostfilm.get_series(
            library, qbt, cfg.qbittorrent.download_dir,
            cfg.lostfilm.torrent_mirror, cfg.lostfilm.lf_session,
            codes, cfg.proxy.as_dict, tracker=tracker,
        )
        logger.info(f'LostFilm [{code}]: added {len(added)} episodes')
        return added
    except Exception as e:
        logger.error(f'LostFilm [{code}]: failed: {e}')
        return []


def check_lostfilm_movie(code):
    """Check one LostFilm movie. Fully isolated."""
    try:
        cfg, db, library, tracker, qbt = _load_env()
        added = lostfilm.get_movie(
            qbt, cfg.qbittorrent.movies_dir,
            cfg.lostfilm.torrent_mirror, cfg.lostfilm.lf_session,
            code, cfg.proxy.as_dict, tracker=tracker,
        )
        logger.info(f'LostFilm movie [{code}]: added {len(added)}')
        return added
    except Exception as e:
        logger.error(f'LostFilm movie [{code}]: failed: {e}')
        return []


def check_anilibria_show(code):
    """Check one Anilibria show for new episodes. Fully isolated."""
    try:
        cfg, db, library, tracker, qbt = _load_env()
        codes = [{'code': code}]
        added = anilibria.get_series(
            library, qbt, cfg.qbittorrent.download_dir,
            cfg.anilibria.torrent_mirror, cfg.anilibria.api_mirror,
            codes, cfg.proxy.as_dict, tracker=tracker,
        )
        logger.info(f'Anilibria [{code}]: added {len(added)} episodes')
        return added
    except Exception as e:
        logger.error(f'Anilibria [{code}]: failed: {e}')
        return []
