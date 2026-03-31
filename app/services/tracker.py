import logging
import os
import time
import requests

from tinydb import Query, TinyDB

logger = logging.getLogger(__name__)

# qBittorrent states grouped by meaning
DOWNLOADING_STATES = {
    'downloading', 'stalledDL', 'forcedDL', 'queuedDL',
    'checkingDL', 'allocating', 'metaDL', 'pausedDL',
}
COMPLETED_STATES = {'uploading', 'stalledUP', 'forcedUP', 'queuedUP', 'pausedUP', 'checkingUP'}
PROBLEM_STATES = {'missingFiles', 'error'}

STALL_THRESHOLD = 6 * 3600  # 6 hours before alerting on stuck downloads


class Tracker:
    """Tracks torrent lifecycle: added → downloading → completed → verified on NAS."""

    def __init__(self, db_path, tg_token, tg_chat_id):
        self.db = TinyDB(db_path)
        self.tg_token = tg_token
        self.tg_chat_id = tg_chat_id

    def record(self, label, save_path):
        """Record a newly added torrent for tracking."""
        q = Query()
        if self.db.search((q.label == label) & (q.save_path == save_path)):
            return  # already tracked

        self.db.insert({
            'label': label,         # e.g. "Захват S03E01"
            'save_path': save_path, # e.g. "/downloads/TV Shows/Захват (2019)/Season 03"
            'added_at': int(time.time()),
            'status': 'downloading',
            'alerted': False,
        })
        logger.info(f'Tracker: recording {label}')

    def check(self, qbt_client, library_dir):
        """Check all tracked downloads against qBittorrent state and NAS filesystem."""
        q = Query()
        active = self.db.search(q.status == 'downloading')
        if not active:
            return

        logger.info(f'Tracker: checking {len(active)} active downloads')

        # Build index of all torrents by save_path
        try:
            torrents = qbt_client.torrents()
        except Exception as e:
            logger.warning(f'Tracker: cannot query qBittorrent: {e}')
            return

        for record in active:
            label = record['label']
            save_path = record['save_path']
            added_at = record['added_at']

            # Find matching torrent(s) by save_path
            matching = [t for t in torrents if t.get('save_path', '').rstrip('/') == save_path.rstrip('/')]

            if not matching:
                # Torrent disappeared from qBittorrent
                age = int(time.time()) - added_at
                if age > STALL_THRESHOLD and not record.get('alerted'):
                    self._alert(f'⚠️ <b>{label}</b>\nТоррент пропал из qBittorrent')
                    self.db.update({'alerted': True}, (q.label == label) & (q.save_path == save_path))
                continue

            # Check state of matching torrents
            states = {t.get('state', '') for t in matching}
            progresses = [t.get('progress', 0) for t in matching]

            # Completed in qBittorrent?
            if states & COMPLETED_STATES and all(p >= 1.0 for p in progresses):
                # Verify file exists on NAS
                # save_path is like /downloads/TV Shows/Show/Season 03 or /downloads/Movies/Film
                # NAS root is library_dir's parent (e.g. /library)
                # Map /downloads/X/... → /library/X/...
                relative = save_path.split('/downloads/', 1)[-1] if '/downloads/' in save_path else save_path
                nas_root = os.path.dirname(library_dir)  # /library
                nas_path = f'{nas_root}/{relative}'

                if self._has_video_files(nas_path):
                    self._notify(f'✅ <b>{label}</b>\nСкачан и на NAS')
                    self.db.update({'status': 'verified'}, (q.label == label) & (q.save_path == save_path))
                else:
                    if not record.get('alerted'):
                        self._alert(f'⚠️ <b>{label}</b>\nСкачан, но НЕ перемещён на NAS\nПуть: {nas_path}')
                        self.db.update({'alerted': True}, (q.label == label) & (q.save_path == save_path))

            # Problem state?
            elif states & PROBLEM_STATES:
                if not record.get('alerted'):
                    state_str = ', '.join(states)
                    self._alert(f'⚠️ <b>{label}</b>\nПроблема с торрентом: {state_str}')
                    self.db.update({'alerted': True}, (q.label == label) & (q.save_path == save_path))

            # Still downloading — check if stuck
            elif states & DOWNLOADING_STATES:
                age = int(time.time()) - added_at
                if age > STALL_THRESHOLD and not record.get('alerted'):
                    progress_pct = max(progresses) * 100
                    self._alert(f'⚠️ <b>{label}</b>\nКачается уже {age // 3600}ч, прогресс: {progress_pct:.0f}%')
                    self.db.update({'alerted': True}, (q.label == label) & (q.save_path == save_path))

    @staticmethod
    def _has_video_files(directory):
        import os
        extensions = {'.mkv', '.avi', '.mp4', '.ts', '.m4v'}
        try:
            for f in os.listdir(directory):
                if os.path.splitext(f)[1].lower() in extensions:
                    return True
        except FileNotFoundError:
            pass
        return False

    def _send_tg(self, text):
        if not self.tg_token or not self.tg_chat_id:
            return
        try:
            requests.post(
                f'https://api.telegram.org/bot{self.tg_token}/sendMessage',
                data={'chat_id': self.tg_chat_id, 'text': text, 'parse_mode': 'HTML'},
                timeout=10,
            )
        except Exception as e:
            logger.warning(f'Tracker: Telegram send failed: {e}')

    def _alert(self, msg):
        logger.warning(f'Tracker alert: {msg}')
        self._send_tg(msg)

    def _notify(self, msg):
        logger.info(f'Tracker: {msg}')
        self._send_tg(msg)
