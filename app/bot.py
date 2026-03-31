import os
import logging
import threading

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import from_file
from services.database import Database
from worker import check_lostfilm_show, check_lostfilm_movie, check_anilibria_show


logger = logging.getLogger(__name__)
log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
logging.getLogger('httpx').setLevel(logging.WARNING)


class Bot:
    def __init__(self, token, db):
        self.db = db
        self.app = ApplicationBuilder().token(token).build()
        self.app.add_handler(CommandHandler('start', self.cmd_start))
        self.app.add_handler(CommandHandler('download', self.cmd_download))
        self.app.add_handler(CommandHandler('list', self.cmd_list))

    def run(self):
        logger.info('Bot started polling...')
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    @staticmethod
    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            'Commands:\n'
            '/download <link> - add a show or movie from LostFilm or Anilibria\n'
            '/list - show tracked series and movies'
        )

    async def cmd_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            await update.message.reply_text('Usage: /download <link>')
            return

        url = args[0]
        logger.info(f'Download request: {url}')

        import re
        lf_match = re.search(r'lostfilm\.\w+/series/([^/]+)', url)
        lf_movie = re.search(r'lostfilm\.\w+/movies/([^/]+)', url)
        al_match = re.search(r'anilibria\.\w+/release/([^/.]+)', url)

        if lf_movie:
            code = lf_movie.group(1)
            self.db.save_new_movie_code(code)
            await update.message.reply_text(f'Added LostFilm movie: {code}\nЗапускаю проверку...')
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
        mv_codes = self.db.get_movie_codes()

        lines = []
        if lf_codes:
            lines.append('LostFilm:')
            for item in lf_codes:
                lines.append(f'  - {item["code"]}')
        if al_codes:
            lines.append('Anilibria:')
            for item in al_codes:
                lines.append(f'  - {item["code"]}')
        if mv_codes:
            lines.append('Movies:')
            for item in mv_codes:
                lines.append(f'  - {item["code"]}')

        if not lines:
            await update.message.reply_text('No tracked shows.')
        else:
            await update.message.reply_text('\n'.join(lines))

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
            token = self.app.bot.token
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': msg},
                timeout=10,
            )
        except Exception as e:
            logger.error(f'Failed to send check result: {e}')

def main():
    cfg = from_file(os.path.abspath('config.yaml'))
    db = Database(cfg.anilibria.db_path, cfg.lostfilm.db_path)

    bot = Bot(token=cfg.nocron.token, db=db)
    bot.run()


if __name__ == '__main__':
    main()
