import os
import re
import logging
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from config import from_file
from services.database import Database
from worker import check_lostfilm_show, check_lostfilm_movie, check_anilibria_show


logger = logging.getLogger(__name__)
log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
logging.getLogger('httpx').setLevel(logging.WARNING)

from collections import OrderedDict

LIBRARY_ROOT = '/library'
VIDEO_EXTENSIONS = {'.mkv', '.avi', '.mp4', '.ts', '.m4v'}
PATH_MAP_MAX_SIZE = 5000
BROWSE_ROOTS = {
    'Сериалы': '/library/TV Shows',
    'Фильмы': '/library/Movies',
    'Аниме': '/library/Anime',
}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB


class Bot:
    def __init__(self, token, db, base_url=None):
        self.db = db
        self._path_map = OrderedDict()  # short_id → full path, bounded
        self._path_counter = 0
        builder = ApplicationBuilder().token(token)
        if base_url:
            builder = builder.base_url(f'{base_url}/bot').base_file_url(f'{base_url}/file/bot')
        self.app = builder.build()
        self.app.add_handler(CommandHandler('start', self.cmd_start))
        self.app.add_handler(CommandHandler('download', self.cmd_download))
        self.app.add_handler(CommandHandler('list', self.cmd_list))
        self.app.add_handler(CommandHandler('browse', self.cmd_browse))
        self.app.add_handler(CallbackQueryHandler(self.on_callback))

    def run(self):
        logger.info('Bot started polling...')
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    # --- Commands ---

    @staticmethod
    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            'Commands:\n'
            '/download <link> - add a show or movie\n'
            '/browse - browse library on NAS\n'
            '/list - show tracked series'
        )

    async def cmd_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            await update.message.reply_text('Usage: /download <link>')
            return

        url = args[0]
        logger.info(f'Download request: {url}')

        lf_match = re.search(r'lostfilm\.\w+/series/([^/?#]+)', url)
        lf_movie = re.search(r'lostfilm\.\w+/movies/([^/?#]+)', url)
        al_match = re.search(r'anilibria\.\w+/release/([^/.?#]+)', url)

        if lf_movie:
            code = lf_movie.group(1)
            await update.message.reply_text(f'LostFilm movie: {code}\nСкачиваю...')
            threading.Thread(
                target=self._check_and_reply,
                args=(update.effective_chat.id, 'lostfilm_movie', code),
                daemon=True,
            ).start()

        elif lf_match:
            code = lf_match.group(1)
            self.db.save_new_lostfilm_code(code)
            await update.message.reply_text(f'Added LostFilm show: {code}\nЗапускаю проверку...')
            threading.Thread(
                target=self._check_and_reply,
                args=(update.effective_chat.id, 'lostfilm', code),
                daemon=True,
            ).start()

        elif al_match:
            code = al_match.group(1)
            self.db.save_new_anilibria_code(code)
            await update.message.reply_text(f'Added Anilibria show: {code}\nЗапускаю проверку...')
            threading.Thread(
                target=self._check_and_reply,
                args=(update.effective_chat.id, 'anilibria', code),
                daemon=True,
            ).start()

        else:
            await update.message.reply_text('Unsupported link. Use LostFilm or Anilibria URLs.')

    async def cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        lf_codes = self.db.get_lostfilm_codes()
        al_codes = self.db.get_anilibria_codes()
        lines = []
        if lf_codes:
            lines.append('LostFilm:')
            for item in lf_codes:
                lines.append(f'  - {item["code"]}')
        if al_codes:
            lines.append('Anilibria:')
            for item in al_codes:
                lines.append(f'  - {item["code"]}')
        if not lines:
            await update.message.reply_text('No tracked shows.')
        else:
            await update.message.reply_text('\n'.join(lines))

    async def cmd_browse(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show top-level categories."""
        buttons = []
        for label, path in BROWSE_ROOTS.items():
            if os.path.isdir(path):
                buttons.append([InlineKeyboardButton(label, callback_data=f'b:{self._short_id(path)}')])
        if not buttons:
            await update.message.reply_text('Библиотека пуста.')
            return
        await update.message.reply_text('📺 Библиотека:', reply_markup=InlineKeyboardMarkup(buttons))

    def _short_id(self, path):
        """Map a path to a short ID for callback_data (64 byte limit)."""
        self._path_counter += 1
        sid = str(self._path_counter)
        self._path_map[sid] = path
        while len(self._path_map) > PATH_MAP_MAX_SIZE:
            self._path_map.popitem(last=False)
        return sid

    # --- Callback handler ---

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == 'b:__root__':
            buttons = []
            for label, path in BROWSE_ROOTS.items():
                if os.path.isdir(path):
                    buttons.append([InlineKeyboardButton(label, callback_data=f'b:{self._short_id(path)}')])
            await query.edit_message_text('📺 Библиотека:', reply_markup=InlineKeyboardMarkup(buttons))
            return

        prefix, sid = data.split(':', 1)
        rel_path = self._path_map.get(sid)
        if not rel_path:
            await query.edit_message_text('Сессия истекла. Нажми /browse заново.')
            return

        if prefix == 'b':
            await self._browse_dir(query, rel_path)
        elif prefix == 'f':
            await self._send_file(query, rel_path)

    async def _browse_dir(self, query, abs_path):
        """Browse a directory, show subdirs and video files."""
        if not os.path.isdir(abs_path):
            await query.edit_message_text('Папка не найдена.')
            return

        entries = sorted(os.listdir(abs_path))
        buttons = []

        # Subdirectories
        dirs = [e for e in entries if os.path.isdir(os.path.join(abs_path, e))]
        for d in dirs:
            child_path = os.path.join(abs_path, d)
            buttons.append([InlineKeyboardButton(f'📁 {d}', callback_data=f'b:{self._short_id(child_path)}')])

        # Video files
        files = [e for e in entries if os.path.splitext(e)[1].lower() in VIDEO_EXTENSIONS]
        for f in files:
            file_path = os.path.join(abs_path, f)
            size = os.path.getsize(file_path)
            size_str = f'{size / (1024**3):.1f}GB' if size >= 1024**3 else f'{size / (1024**2):.0f}MB'
            label = f'🎬 {f} ({size_str})'
            if len(label) > 60:
                label = f'🎬 {f[:45]}... ({size_str})'
            buttons.append([InlineKeyboardButton(label, callback_data=f'f:{self._short_id(file_path)}')])

        # Back button
        parent = os.path.dirname(abs_path)
        # Only show back if not at a root level
        is_root = abs_path in BROWSE_ROOTS.values()
        if not is_root:
            buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data=f'b:{self._short_id(parent)}')])
        else:
            buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='b:__root__')])

        if not dirs and not files:
            await query.edit_message_text(f'📂 {os.path.basename(abs_path)}\n\nПусто.')
            return

        title = os.path.basename(abs_path)
        await query.edit_message_text(
            f'📂 {title}',
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def _send_file(self, query, abs_path):
        """Send a video file from NAS. Convert to Telegram-compatible MP4 H.264 if needed."""
        import subprocess
        import tempfile

        if not os.path.isfile(abs_path):
            await query.edit_message_text('Файл не найден.')
            return

        filename = os.path.basename(abs_path)
        ext = os.path.splitext(abs_path)[1].lower()
        send_path = abs_path
        tmp_path = None

        try:
            chat_id = query.message.chat_id

            # Probe video: codec, width, height
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name,width,height', '-of', 'csv=p=0', abs_path],
                capture_output=True, text=True, timeout=10,
            )
            parts = probe.stdout.strip().split(',')
            video_codec = parts[0] if len(parts) >= 1 else ''
            width = int(parts[1]) if len(parts) >= 2 else 0
            height = int(parts[2]) if len(parts) >= 3 else 0

            needs_remux = ext in {'.mkv', '.ts', '.m4v'} and video_codec in ('h264', 'hevc')
            needs_reencode = ext in VIDEO_EXTENSIONS and video_codec not in ('h264', 'hevc')

            await query.edit_message_text(f'⏳ Подготовка...')

            if needs_remux:
                # Fast remux — copy codec, change container to MP4 (instant)
                tmp_path = tempfile.mktemp(suffix='.mp4', dir='/tmp')
                result = subprocess.run(
                    ['ffmpeg', '-y', '-i', abs_path, '-c', 'copy', '-movflags', '+faststart', tmp_path],
                    capture_output=True, timeout=120,
                )
                if result.returncode == 0 and os.path.isfile(tmp_path):
                    send_path = tmp_path
                    filename = os.path.splitext(filename)[0] + '.mp4'
                else:
                    logger.warning(f'Remux failed: {result.stderr[-200:]}')

            elif needs_reencode:
                tmp_path = tempfile.mktemp(suffix='.mp4', dir='/tmp')
                result = subprocess.run(
                    ['ffmpeg', '-y', '-i', abs_path,
                     '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                     '-c:a', 'aac', '-b:a', '192k',
                     '-movflags', '+faststart',
                     '-max_muxing_queue_size', '1024',
                     tmp_path],
                    capture_output=True, timeout=1800,
                )
                if result.returncode == 0 and os.path.isfile(tmp_path):
                    send_path = tmp_path
                    filename = os.path.splitext(filename)[0] + '.mp4'
                    # Re-probe converted file for correct dimensions
                    probe2 = subprocess.run(
                        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                         '-show_entries', 'stream=width,height', '-of', 'csv=p=0', tmp_path],
                        capture_output=True, text=True, timeout=10,
                    )
                    p2 = probe2.stdout.strip().split(',')
                    if len(p2) == 2:
                        width, height = int(p2[0]), int(p2[1])
                else:
                    logger.warning(f'Re-encode failed: {result.stderr[-300:]}')

            # If still too big — re-encode to fit under 2GB
            size = os.path.getsize(send_path)
            if size > MAX_FILE_SIZE:
                # Get duration to calculate target bitrate
                dur_probe = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'csv=p=0', abs_path],
                    capture_output=True, text=True, timeout=10,
                )
                duration = float(dur_probe.stdout.strip() or '3600')
                # Target: 1.9GB to leave margin, in kbps
                target_bitrate = int((1.9 * 1024 * 1024 * 8) / duration)

                if tmp_path and os.path.isfile(tmp_path):
                    os.remove(tmp_path)
                tmp_path = tempfile.mktemp(suffix='.mp4', dir='/tmp')
                result = subprocess.run(
                    ['ffmpeg', '-y', '-i', abs_path,
                     '-c:v', 'libx264', '-preset', 'fast',
                     '-b:v', f'{target_bitrate}k', '-maxrate', f'{target_bitrate}k',
                     '-bufsize', f'{target_bitrate * 2}k',
                     '-vf', 'scale=-2:720',
                     '-c:a', 'aac', '-b:a', '192k',
                     '-movflags', '+faststart',
                     '-max_muxing_queue_size', '1024',
                     tmp_path],
                    capture_output=True, timeout=3600,
                )
                if result.returncode == 0 and os.path.isfile(tmp_path):
                    send_path = tmp_path
                    filename = os.path.splitext(os.path.basename(abs_path))[0] + '.mp4'
                    # Re-probe dimensions
                    p3 = subprocess.run(
                        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                         '-show_entries', 'stream=width,height', '-of', 'csv=p=0', tmp_path],
                        capture_output=True, text=True, timeout=10,
                    )
                    parts3 = p3.stdout.strip().split(',')
                    if len(parts3) == 2:
                        width, height = int(parts3[0]), int(parts3[1])
                else:
                    logger.error(f'Compression failed: {result.stderr[-300:]}')
                    await query.edit_message_text('❌ Не удалось сжать файл')
                    return

            size = os.path.getsize(send_path)

            with open(send_path, 'rb') as f:
                await query.get_bot().send_video(
                    chat_id=chat_id,
                    video=f,
                    filename=filename,
                    width=width or None,
                    height=height or None,
                    supports_streaming=True,
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                )
            # Delete "Подготовка..." message after video is sent
            try:
                await query.message.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f'Failed to send file {abs_path}: {e}')
            chat_id = query.message.chat_id
            await query.get_bot().send_message(chat_id=chat_id, text=f'❌ Ошибка отправки: {e}')
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                os.remove(tmp_path)

    # --- Background check helper ---

    def _check_and_reply(self, chat_id, provider, code):
        """Run check in background thread. Only notify on errors."""
        try:
            if provider == 'lostfilm':
                check_lostfilm_show(code)
            elif provider == 'lostfilm_movie':
                check_lostfilm_movie(code)
            else:
                check_anilibria_show(code)
        except Exception as e:
            logger.error(f'Immediate check failed for {code}: {e}')
            try:
                import requests
                base = os.environ.get('TG_BOT_API_URL', 'https://api.telegram.org')
                token = self.app.bot.token
                requests.post(
                    f'{base}/bot{token}/sendMessage',
                    data={'chat_id': chat_id, 'text': f'❌ {code}: ошибка при проверке: {e}'},
                    timeout=10,
                )
            except Exception:
                pass


def main():
    cfg = from_file(os.path.abspath('config.yaml'))
    db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)

    base_url = os.environ.get('TG_BOT_API_URL')
    bot = Bot(token=cfg.nocron.token, db=db, base_url=base_url)
    bot.run()


if __name__ == '__main__':
    main()
