import os
import logging
import asyncio

from telegram import ForceReply, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

import domain.config as config
from services.dbcontroller import DbController

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class NocronBot:
    def __init__(self, token, lostfilm_host, anilibria_host, db):
        self.application = ApplicationBuilder().token(token).build()
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('download', self.download_command))
        self.lostfilm_host = lostfilm_host
        self.anilibria_host = anilibria_host
        self.db = db

    async def run(self):
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await update.message.reply_html(
            rf'Hi {user.mention_html()}! Use /download LINK for queue.'
        )

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text
        logger.info('NEW Event from bot: ' + text)

        args = text.split(' ')
        if len(args) < 2:
            await update.message.reply_text('Link is empty.')

        url = args[1]
        if await self.is_lostfilm(url):
            await self.process_lostfilm_url(update.message, url)
        elif await self.is_anilibria(url):
            await self.process_anilibria_url(update.message, url)
        else:
            await update.message.reply_text('Invalid link.')

    async def is_lostfilm(self, url) -> bool:
        return url.startswith(self.lostfilm_host)

    async def is_anilibria(self, url) -> bool:
        return url.startswith(self.anilibria_host)

    async def process_lostfilm_url(self, message, url) -> None:
        code = await self.extract_lostfilm_series_name(url)
        if code:
            self.db.save_new_lostfilm_code(code)
            await message.reply_text('Queue lostfilm TV Show!')
        else:
            await message.reply_text('Unable to extract lostfilm code!')

    async def process_anilibria_url(self, message, url) -> None:
        code = await self.extract_anilibria_series_name(url)
        if code:
            self.db.save_new_anilibria_code(code)
            await message.reply_text('Queue anilibria TV Show!')
        else:
            await message.reply_text('Unable to extract anilibria code!')

    async def extract_lostfilm_series_name(self, url) -> str:
        return self.find_between(url, self.lostfilm_host + '/series/', '/')

    async def extract_anilibria_series_name(self, url) -> str:
        return self.find_between(url, self.anilibria_host + '/release/', '.html')

    @staticmethod
    def find_between(s, first, last) -> str:
        try:
            start = s.index(first) + len(first)
            end = s.index(last, start)
            return s[start:end]
        except ValueError:
            return ""


if __name__ == '__main__':
    logger.info('Reading config...')
    cfg_path = os.path.abspath('config.yaml')
    cfg = config.from_file(cfg_path)

    logger.info('Init db...')
    db = DbController(cfg.qbittorrent.db_path, cfg.anilibria.db_path, cfg.lostfilm.db_path)

    logger.info('Setup nocron bot...')
    bot = NocronBot(cfg.nocron.token, cfg.lostfilm.torrent_mirror, cfg.anilibria.torrent_mirror, db)
    asyncio.run(bot.run())
