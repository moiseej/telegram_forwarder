"""Telegram commands for group administrators to manage topic bindings."""
from telegram.error import TelegramError
from telegram.ext import CommandHandler

from .store import RouteStore

HELP = (
    "Добавьте бота администратором в группу с темами.\n"
    "В нужной теме: /bind к — назначить её для /к.\n"
    "Затем в этой группе: /к ваш текст (или фото с такой подписью).\n"
    "/routes — назначения этой группы.\n"
    "/unbind к — удалить назначение.\n"
    "Настройка доступна администраторам группы от личного имени.\n"
    "В каждой группе свои команды. Пересылка выполняется внутри группы.\n\n"
    "Когда бот добавлен во все нужные группы, запретите новые добавления: "
    "@BotFather → выберите бота → Настройки бота → Allow Groups → отключить. "
    "Из уже подключённых групп бот не удалится."
)


class AdminCommands:
    def __init__(self, store: RouteStore):
        self.store = store

    async def help(self, update, context):
        if update.message:
            await update.message.reply_text(HELP)

    async def authorize(self, message, bot, require_manage_topics: bool = False) -> bool:
        if message.chat.type != "supergroup" or not message.chat.is_forum:
            await message.reply_text("Настраивайте бота в группе с включёнными темами.")
            return False
        if message.sender_chat or not message.from_user or message.from_user.is_bot:
            await message.reply_text("Отправьте команду от личного имени администратора.")
            return False
        try:
            member = await bot.get_chat_member(message.chat_id, message.from_user.id)
            own = await bot.get_chat_member(message.chat_id, bot.id)
        except TelegramError:
            await message.reply_text("Не удалось проверить права. Назначьте бота администратором и повторите.")
            return False
        if member.status not in ("administrator", "creator"):
            await message.reply_text("Менять назначения могут только администраторы группы.")
            return False
        if own.status != "administrator":
            await message.reply_text("Сначала назначьте бота администратором группы.")
            return False
        if require_manage_topics and not getattr(own, "can_manage_topics", False):
            await message.reply_text("В правах администратора бота включите «Управление темами», затем повторите /bind.")
            return False
        return True

    async def bind(self, update, context):
        message = update.message
        if not message or not await self.authorize(message, context.bot, require_manage_topics=True):
            return
        if len(context.args) != 1:
            await message.reply_text("В нужной теме отправьте /bind к (один код команды).")
            return
        if not message.is_topic_message or not message.message_thread_id:
            await message.reply_text("Откройте нужную отдельную тему и повторите /bind. Общая тема не поддерживается.")
            return
        try:
            code = self.store.bind(message.chat_id, context.args[0], message.message_thread_id)
        except ValueError as error:
            await message.reply_text(str(error))
            return
        await message.reply_text(f"Готово: {code} → эта тема. Теперь отправьте {code} текст в любом месте этой группы.")

    async def unbind(self, update, context):
        message = update.message
        if not message or not await self.authorize(message, context.bot):
            return
        if len(context.args) != 1:
            await message.reply_text("Использование: /unbind к")
            return
        try:
            removed = self.store.unbind(message.chat_id, context.args[0])
        except ValueError as error:
            await message.reply_text(str(error))
            return
        await message.reply_text("Назначение удалено." if removed else "Такого назначения нет.")

    async def routes(self, update, context):
        message = update.message
        if not message:
            return
        topics = self.store.config_for(message.chat_id).topics
        lines = [f"{code} → тема {topic}" for code, topic in topics.items()]
        await message.reply_text("\n".join(lines) or "Назначений нет. В нужной теме администратор может отправить /bind к.")

    def handlers(self):
        return [CommandHandler(["start", "help"], self.help), CommandHandler("bind", self.bind),
                CommandHandler("unbind", self.unbind), CommandHandler("routes", self.routes)]
