"""Telegram update handling and application startup."""
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from .config import Config, load_config
from .delivery import send_to_topic
from .routing import format_message, parse_command

logger = logging.getLogger(__name__)


def make_handler(config: Config):
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message or message.chat_id != config.chat_id:
            return
        user = message.from_user
        if user and user.is_bot:
            return
        route = parse_command(message.text or message.caption or "", config.topics, context.bot.username)
        if route is None:
            return
        if not route.text and not message.photo:
            await message.reply_text(f"Добавьте текст после команды {route.command}.")
            return
        author = f"@{user.username}" if user and user.username else user.full_name if user else "Неизвестный пользователь"
        text = format_message(author, route.text)
        photo = message.photo[-1].file_id if message.photo else None
        # Telegram counts text lengths in UTF-16 code units.
        if len(text.encode("utf-16-le")) // 2 > (1024 if photo else 4096):
            await message.reply_text("Сообщение с подписью автора слишком длинное. Сократите текст.")
            return
        await send_to_topic(context.bot, config.chat_id, route.topic_id, text, photo)
        logger.info("Sent message_id=%s to topic=%s", message.message_id, route.topic_id)
    return handle


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Avoid logging request URLs or user messages, which may contain secrets.
    logger.error("Telegram update failed (%s)", type(context.error).__name__)


def main() -> None:
    token = os.getenv("TOPIC_FORWARD_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Задайте TOPIC_FORWARD_BOT_TOKEN")
    config = load_config(Path(__file__).resolve().parents[1] / "config.yaml")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.StatusUpdate.ALL, make_handler(config)))
    app.add_error_handler(on_error)
    app.run_polling(drop_pending_updates=True, allowed_updates=["message"])
