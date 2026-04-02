import re
import time
import logging
from qbittorrent import Client
from services import network

INDEX_TTL = 30  # seconds before re-indexing


logger = logging.getLogger(__name__)

# Any torrent that exists in qBittorrent should be skipped — don't re-download
SKIP_STATES = {'downloading', 'stalledDL', 'uploading', 'stalledUP',
               'forcedUP', 'forcedDL', 'queuedDL', 'queuedUP',
               'checkingDL', 'checkingUP', 'pausedUP', 'pausedDL',
               'moving', 'allocating', 'metaDL',
               'missingFiles', 'error'}


class QBittorrent:
    def __init__(self, host, port, username, password):
        url = f'http://{host}:{port}/'
        self.client = Client(url)
        self.client.login(username=username, password=password)
        self._torrents_by_name = self._index_torrents()
        self._index_time = time.monotonic()

    def _ensure_fresh_index(self):
        if time.monotonic() - self._index_time > INDEX_TTL:
            self._torrents_by_name = self._index_torrents()
            self._index_time = time.monotonic()

    def _index_torrents(self):
        """Build index: torrent name -> list of (hash, state, save_path, progress)."""
        index = {}
        try:
            for t in self.client.torrents():
                name = t.get('name', '')
                entry = {
                    'hash': t.get('hash', ''),
                    'state': t.get('state', ''),
                    'save_path': t.get('save_path', ''),
                    'progress': t.get('progress', 0),
                }
                index.setdefault(name, []).append(entry)
        except Exception as e:
            logger.warning(f'Could not index torrents: {e}')
        total = sum(len(v) for v in index.values())
        logger.info(f'qBittorrent: indexed {total} torrents')
        return index

    def episode_in_queue(self, show_code, season_num, episode_num):
        """Check if episode is already queued/downloading/seeding in qBittorrent."""
        self._ensure_fresh_index()

        pattern = re.compile(
            rf'[Ss]{int(season_num):02d}[Ee]{int(episode_num):02d}',
        )
        code_pattern = show_code.replace('_', '.')

        for name, entries in self._torrents_by_name.items():
            if code_pattern.lower() not in name.lower():
                continue
            if not pattern.search(name):
                continue
            for entry in entries:
                if entry['state'] in SKIP_STATES:
                    return True
        return False

    def download_torrent(self, torrent_url, save_path, proxies=None, tracker=None, label=None):
        logger.info(f'Downloading torrent: {torrent_url}')
        response = network.get(torrent_url, proxies=proxies)
        self.client.download_from_file(response.content, save_path=save_path)
        logger.info(f'Added to qBittorrent -> {save_path}')
        if tracker and label:
            tracker.record(label, save_path)
