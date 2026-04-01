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

LIBRARY_ROOT = '/library'
VIDEO_EXTENSIONS = {'.mkv', '.avi', '.mp4', '.ts', '.m4v'}
BROWSE_ROOTS = {
    'Сериалы': '/library/TV Shows',
    'Фильмы': '/library/Movies',
    'Аниме': '/library/Anime',
}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB


class Bot:
    def __init__(self, token, db, base_url=None):
        self.db = db
        self._path_map = {}  # short_id → full path
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

        lf_match = re.search(r'lostfilm\.\w+/series/([^/]+)', url)
        lf_movie = re.search(r'lostfilm\.\w+/movies/([^/]+)', url)
        al_match = re.search(r'anilibria\.\w+/release/([^/.]+)', url)

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
        """Send a video file from NAS. Remux to MP4 if needed for Telegram playback."""
        if not os.path.isfile(abs_path):
            await query.edit_message_text('Файл не найден.')
            return

        size = os.path.getsize(abs_path)
        if size > MAX_FILE_SIZE:
            size_gb = size / (1024**3)
            await query.edit_message_text(f'❌ Файл слишком большой: {size_gb:.1f}GB (лимит 2GB)')
            return

        filename = os.path.basename(abs_path)
        size_str = f'{size / (1024**3):.1f}GB' if size >= 1024**3 else f'{size / (1024**2):.0f}MB'
        ext = os.path.splitext(abs_path)[1].lower()
        send_path = abs_path
        tmp_path = None

        try:
            chat_id = query.message.chat_id

            # Remux non-MP4 video to MP4 for Telegram inline playback
            if ext in {'.mkv', '.avi', '.ts', '.m4v'}:
                import subprocess
                import tempfile
                await query.edit_message_text(f'🔄 Конвертирую {filename} в MP4...')
                tmp_path = tempfile.mktemp(suffix='.mp4', dir='/tmp')
                result = subprocess.run(
                    ['ffmpeg', '-i', abs_path, '-c', 'copy', '-movflags', '+faststart', tmp_path],
                    capture_output=True, timeout=300,
                )
                if result.returncode == 0 and os.path.isfile(tmp_path):
                    send_path = tmp_path
                    filename = os.path.splitext(filename)[0] + '.mp4'
                    size = os.path.getsize(tmp_path)
                    size_str = f'{size / (1024**3):.1f}GB' if size >= 1024**3 else f'{size / (1024**2):.0f}MB'
                else:
                    logger.warning(f'ffmpeg remux failed: {result.stderr[:200]}')
                    # Fall back to sending as-is

            await query.edit_message_text(f'⏳ Отправляю {filename} ({size_str})...')

            with open(send_path, 'rb') as f:
                if ext in {'.mkv', '.mp4', '.avi', '.m4v', '.ts'}:
                    await query.get_bot().send_video(
                        chat_id=chat_id,
                        video=f,
                        filename=filename,
                        supports_streaming=True,
                        read_timeout=600,
                        write_timeout=600,
                        connect_timeout=60,
                    )
                else:
                    await query.get_bot().send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=filename,
                        read_timeout=600,
                        write_timeout=600,
                        connect_timeout=60,
                    )
            await query.get_bot().send_message(chat_id=chat_id, text=f'✅ {filename}')
        except Exception as e:
            logger.error(f'Failed to send file {abs_path}: {e}')
            chat_id = query.message.chat_id
            await query.get_bot().send_message(chat_id=chat_id, text=f'❌ Ошибка отправки: {e}')
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                os.remove(tmp_path)

    # --- Background check helper ---

    def _check_and_reply(self, chat_id, provider, code):
        """Run check in background thread and send result to Telegram."""
        import requests
        try:
            if provider == 'lostfilm':
                added = check_lostfilm_show(code)
            elif provider == 'lostfilm_movie':
                added = check_lostfilm_movie(code)
            else:
                added = check_anilibria_show(code)

            if added:
                msg = f'✅ {code}: добавлено {len(added)} эпизодов\n' + '\n'.join(added)
            else:
                msg = f'ℹ️ {code}: новых эпизодов не найдено'
        except Exception as e:
            msg = f'❌ {code}: ошибка при проверке: {e}'
            logger.error(f'Immediate check failed for {code}: {e}')

        try:
            base = os.environ.get('TG_BOT_API_URL', 'https://api.telegram.org')
            token = self.app.bot.token
            requests.post(
                f'{base}/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': msg},
                timeout=10,
            )
        except Exception as e:
            logger.error(f'Failed to send check result: {e}')


def main():
    cfg = from_file(os.path.abspath('config.yaml'))
    db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)

    base_url = os.environ.get('TG_BOT_API_URL')
    bot = Bot(token=cfg.nocron.token, db=db, base_url=base_url)
    bot.run()


if __name__ == '__main__':
    main()
