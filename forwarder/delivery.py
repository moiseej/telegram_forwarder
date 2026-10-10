"""Telegram delivery and one retry for a closed forum topic."""
from telegram.error import BadRequest


async def send_to_topic(bot, chat_id: int, topic_id: int, text: str, photo: str | None = None) -> None:
    kwargs = {"chat_id": chat_id, "message_thread_id": topic_id}
    if photo:
        method = bot.send_photo
        kwargs.update(photo=photo, caption=text)
    else:
        method = bot.send_message
        kwargs.update(text=text)
    try:
        await method(**kwargs)
    except BadRequest as error:
        if "topic_closed" not in str(error).lower().replace(" ", "_"):
            raise
        await bot.reopen_forum_topic(chat_id=chat_id, message_thread_id=topic_id)
        await method(**kwargs)
