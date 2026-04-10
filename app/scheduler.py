"""
Periodic scheduler — each tracked show gets its own random slot within the hour.
Renamer and tracker run every 15 minutes independently.
"""
import os
import random
import time
import threading
import logging

from config import from_file
from services.database import Database
from worker import check_lostfilm_show, check_anilibria_show, _load_env
from services.renamer import Renamer

logger = logging.getLogger(__name__)
log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)

CYCLE_SECONDS = 3600  # 1 hour
MAINTENANCE_INTERVAL = 900  # 15 min for renamer + tracker


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


def schedule_show(delay, provider, code):
    """Sleep `delay` seconds, then check one show."""
    def run():
        time.sleep(delay)
        logger.info(f'Scheduled check: {provider}/{code} (after {delay}s delay)')
        if provider == 'lostfilm':
            check_lostfilm_show(code)
        else:
            check_anilibria_show(code)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def run_maintenance():
    """Run renamer and tracker verification."""
    try:
        cfg, db, library, tracker, qbt = _load_env()
        renamer = Renamer(cfg.renamer.root_dir + '/Anime', cfg.renamer.anilibria_regex)
        unmatched = renamer.rename()
        if unmatched:
            msg = '⚠️ Renamer: unrecognized files (invisible to Plex):\n'
            msg += '\n'.join(f'• {os.path.basename(f)}' for f in unmatched[:10])
            if len(unmatched) > 10:
                msg += f'\n...and {len(unmatched) - 10} more'
            tracker._alert(msg)
        tracker.check(
            qbt.client, cfg.renamer.root_dir,
            qbt_download_dir=cfg.qbittorrent.download_dir.rsplit('/', 1)[0],  # /downloads
            nas_library_dir=cfg.renamer.root_dir,  # /library
        )
    except Exception as e:
        logger.error(f'Maintenance failed: {e}')


def main():
    cfg = from_file(os.path.abspath('config.yaml'))

    logger.info('Waiting for qBittorrent...')
    wait_for_qbittorrent(cfg.qbittorrent.host, cfg.qbittorrent.port)

    # Maintenance loop in background (renamer + tracker every 15 min)
    def maintenance_loop():
        while True:
            time.sleep(MAINTENANCE_INTERVAL)
            logger.info('=== Maintenance: renamer + tracker ===')
            run_maintenance()

    threading.Thread(target=maintenance_loop, daemon=True).start()

    # Main scheduling loop
    while True:
        db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)

        shows = []
        for item in db.get_lostfilm_codes():
            shows.append(('lostfilm', item['code']))
        for item in db.get_anilibria_codes():
            shows.append(('anilibria', item['code']))

        if not shows:
            logger.info('No tracked shows, sleeping 60s...')
            time.sleep(60)
            continue

        # Assign each show a random delay within the hour
        threads = []
        for provider, code in shows:
            delay = random.randint(0, CYCLE_SECONDS - 60)  # leave 60s buffer at end
            logger.info(f'Scheduled {provider}/{code} at +{delay}s ({delay // 60}m{delay % 60}s)')
            threads.append(schedule_show(delay, provider, code))

        # Wait for the full hour to complete, then start next cycle
        logger.info(f'=== Cycle started: {len(shows)} shows spread over {CYCLE_SECONDS}s ===')
        time.sleep(CYCLE_SECONDS)

        # Wait for any stragglers still running
        for t in threads:
            t.join(timeout=120)


if __name__ == '__main__':
    main()
