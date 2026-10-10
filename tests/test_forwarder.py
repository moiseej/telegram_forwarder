import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from telegram.error import BadRequest

from forwarder.app import make_handler
from forwarder.config import Config, load_config
from forwarder.delivery import send_to_topic
from forwarder.errors import delivery_error_message
from forwarder.routing import parse_command


class ConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"
            path.write_text(text, encoding="utf-8")
            return load_config(path)

    def test_valid_and_normalized(self):
        self.assertEqual(self.load("chat_id: -100\ntopics:\n  /К: 12\n"), Config(-100, {"/к": 12}))

    def test_invalid_config(self):
        for text in ["", "[]", "chat_id: 1\ntopics: {к: 12}",
                     "chat_id: -100\ntopics: {}", "chat_id: -100\ntopics: {к: 0}",
                     "chat_id: -100\ntopics: {к: true}",
                     "chat_id: -100\ntopics: {к: 12, /К: 13}",
                     "chat_id: -100\ntopics: {'bad command': 12}"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)


class RoutingTests(unittest.TestCase):
    def test_commands(self):
        topics = {"/к": 12, "/ж": 13, "/и": 14}
        for command, topic in topics.items():
            with self.subTest(command=command):
                result = parse_command(f"  {command.upper()}@MyBot  hello\nworld  ", topics, "mybot")
                self.assertEqual((result.command, result.topic_id, result.text), (command, topic, "hello\nworld"))

    def test_unmatched(self):
        for text in ["", "hello", "/unknown hi", "/кот hi", "/к@other hi", "/к@ hi"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_command(text, {"/к": 12}, "mybot"))


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = NS(username="mybot", send_message=AsyncMock(), send_photo=AsyncMock(), reopen_forum_topic=AsyncMock())
        self.context = NS(bot=self.bot)
        self.message = NS(chat_id=-100, text="/к hello", caption=None, photo=[], message_id=42,
                          from_user=NS(username="alice", full_name="Alice", is_bot=False), reply_text=AsyncMock())
        self.handler = make_handler(Config(-100, {"/к": 12, "/ж": 13, "/и": 14}))

    async def process(self):
        await self.handler(NS(message=self.message), self.context)

    async def test_text_delivery(self):
        await self.process()
        self.bot.send_message.assert_awaited_once_with(chat_id=-100, message_thread_id=12, text="@alice\n\nhello")
        self.bot.send_photo.assert_not_awaited()

    async def test_name_without_username(self):
        self.message.from_user.username = None
        await self.process()
        self.assertEqual(self.bot.send_message.await_args.kwargs["text"], "Alice\n\nhello")

    async def test_missing_author(self):
        self.message.from_user = None
        await self.process()
        self.assertEqual(self.bot.send_message.await_args.kwargs["text"], "Неизвестный пользователь\n\nhello")

    async def test_photo_caption(self):
        self.message.text = None
        self.message.caption = "/ж@mybot picture"
        self.message.photo = [NS(file_id="small"), NS(file_id="large")]
        await self.process()
        self.bot.send_photo.assert_awaited_once_with(chat_id=-100, message_thread_id=13, photo="large", caption="@alice\n\npicture")
        self.bot.send_message.assert_not_awaited()

    async def test_photo_without_text(self):
        self.message.text = None
        self.message.caption = "/и"
        self.message.photo = [NS(file_id="photo")]
        await self.process()
        self.assertEqual(self.bot.send_photo.await_args.kwargs["caption"], "@alice")

    async def test_empty_command(self):
        self.message.text = "/к"
        await self.process()
        self.message.reply_text.assert_awaited_once()
        self.bot.send_message.assert_not_awaited()

    async def test_ignored_updates(self):
        await self.handler(NS(message=None), self.context)
        self.message.chat_id = -999
        await self.process()
        self.message.chat_id = -100
        self.message.from_user.is_bot = True
        await self.process()
        self.message.from_user.is_bot = False
        for text in ["ordinary text", "/к@other hello", "/unknown hello"]:
            self.message.text = text
            await self.process()
        self.bot.send_message.assert_not_awaited()
        self.bot.send_photo.assert_not_awaited()

    async def test_text_length_boundary(self):
        self.message.text = "/к " + "x" * 4088
        await self.process()
        self.bot.send_message.assert_awaited_once()
        self.bot.send_message.reset_mock()
        self.message.text += "x"
        await self.process()
        self.bot.send_message.assert_not_awaited()
        self.message.reply_text.assert_awaited_once()

    async def test_photo_utf16_boundary(self):
        self.message.text = None
        self.message.photo = [NS(file_id="photo")]
        self.message.caption = "/к " + "😀" * 508
        await self.process()
        self.bot.send_photo.assert_awaited_once()
        self.bot.send_photo.reset_mock()
        self.message.caption += "😀"
        await self.process()
        self.bot.send_photo.assert_not_awaited()
        self.message.reply_text.assert_awaited_once()


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_topic_retry_text_and_photo(self):
        for photo in [None, "file"]:
            with self.subTest(photo=photo):
                bot = NS(send_message=AsyncMock(), send_photo=AsyncMock(), reopen_forum_topic=AsyncMock())
                method = bot.send_photo if photo else bot.send_message
                method.side_effect = [BadRequest("TOPIC_CLOSED"), None]
                await send_to_topic(bot, -100, 12, "hello", photo)
                self.assertEqual(method.await_count, 2)
                self.assertEqual(method.await_args_list[0], method.await_args_list[1])
                bot.reopen_forum_topic.assert_awaited_once_with(chat_id=-100, message_thread_id=12)

    async def test_unrelated_error_no_retry(self):
        bot = NS(send_message=AsyncMock(side_effect=BadRequest("Forbidden")), reopen_forum_topic=AsyncMock())
        with self.assertRaises(BadRequest):
            await send_to_topic(bot, -100, 12, "hello")
        bot.send_message.assert_awaited_once()
        bot.reopen_forum_topic.assert_not_awaited()

    async def test_reopen_failure_propagates(self):
        bot = NS(send_message=AsyncMock(side_effect=BadRequest("Topic_closed")),
                 reopen_forum_topic=AsyncMock(side_effect=BadRequest("Not enough rights")))
        with self.assertRaises(BadRequest):
            await send_to_topic(bot, -100, 12, "hello")
        bot.send_message.assert_awaited_once()

    async def test_retry_is_bounded(self):
        bot = NS(send_message=AsyncMock(side_effect=BadRequest("Topic_closed")), reopen_forum_topic=AsyncMock())
        with self.assertRaises(BadRequest):
            await send_to_topic(bot, -100, 12, "hello")
        self.assertEqual(bot.send_message.await_count, 2)
        bot.reopen_forum_topic.assert_awaited_once()


class ErrorMessageTests(unittest.TestCase):
    def test_known_errors_are_actionable(self):
        cases = {
            "Bad Request: message thread not found": "не нашёл тему",
            "Bad Request: TOPIC_CLOSED": "нет права открыть",
            "Forbidden: not enough rights": "Управление темами",
            "Bad Request: chat not found": "не имеет доступа",
            "Bad Request: message is too long": "слишком длинное",
        }
        for error, expected in cases.items():
            with self.subTest(error=error):
                self.assertIn(expected, delivery_error_message(Exception(error)))

    def test_unknown_error_does_not_echo_details(self):
        secret = "sensitive-value"
        self.assertNotIn(secret, delivery_error_message(Exception(secret)))


if __name__ == "__main__":
    unittest.main()
