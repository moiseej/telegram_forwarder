from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from telegram.error import BadRequest
from forwarder.admin import AdminCommands
from forwarder.app import make_handler
from forwarder.config import Config
from forwarder.store import RouteStore, normalize_code


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "routes.sqlite3"
        self.store = RouteStore(self.path)

    def test_persistence_isolation_replace_delete(self):
        self.store.bind(-100, "К", 12)
        self.store.bind(-200, "/к", 20)
        self.store.bind(-100, "к", 13)
        other = RouteStore(self.path)
        self.assertEqual(other.config_for(-100).topics, {"/к": 13})
        self.assertTrue(other.unbind(-100, "к"))
        self.assertFalse(other.unbind(-100, "к"))
        self.assertEqual(self.store.config_for(-100).topics, {})
        self.assertEqual(other.config_for(-200).topics, {"/к": 20})

    def test_legacy_only_once(self):
        path = Path(self.tmp.name) / "legacy.sqlite3"
        legacy = Config(-100, {"/к": 10})
        store = RouteStore(path, legacy)
        self.assertEqual(store.config_for(-100).topics, legacy.topics)
        store.unbind(-100, "к")
        self.assertEqual(RouteStore(path, legacy).config_for(-100).topics, {})

    def test_invalid_codes_and_ids(self):
        for code in ["", "a b", "к@bot", "//к", "bind", "HELP", "x" * 33]:
            with self.subTest(code=code), self.assertRaises(ValueError):
                normalize_code(code)
        for chat, topic in [(100, 1), (-100, 0), (-100, True)]:
            with self.assertRaises(ValueError):
                self.store.bind(chat, "к", topic)

    def test_group_limit(self):
        for index in range(50):
            self.store.bind(-100, f"c{index}", index + 1)
        self.store.bind(-100, "c0", 999)
        with self.assertRaises(ValueError):
            self.store.bind(-100, "extra", 51)
        self.store.bind(-200, "extra", 51)


class AdminTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = RouteStore(Path(self.tmp.name) / "routes.sqlite3")
        self.admin = AdminCommands(self.store)
        self.bot = NS(id=9, username="mybot", get_chat_member=AsyncMock(return_value=NS(status="administrator")),
                      send_message=AsyncMock(), send_photo=AsyncMock(), reopen_forum_topic=AsyncMock())
        self.message = NS(chat_id=-100, chat=NS(type="supergroup", is_forum=True), sender_chat=None,
                          from_user=NS(id=1, is_bot=False, username="alice", full_name="Alice"),
                          is_topic_message=True, message_thread_id=12, reply_text=AsyncMock(),
                          text="/bind к", caption=None, photo=[], message_id=1)
        self.update = NS(message=self.message)
        self.context = NS(bot=self.bot, args=["к"])

    async def test_bind_and_immediate_delivery_then_remove(self):
        handler = make_handler(self.store.config_for)
        await self.admin.bind(self.update, self.context)
        self.message.text = "/к hello"
        await handler(self.update, self.context)
        self.bot.send_message.assert_awaited_once_with(chat_id=-100, message_thread_id=12, text="@alice\n\nhello")
        await self.admin.unbind(self.update, self.context)
        await handler(self.update, self.context)
        self.assertEqual(self.bot.send_message.await_count, 1)

    async def test_non_admin_cannot_bind_or_remove(self):
        self.store.bind(-100, "к", 10)
        self.bot.get_chat_member.side_effect = [NS(status="member"), NS(status="administrator")] * 2
        await self.admin.bind(self.update, self.context)
        await self.admin.unbind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {"/к": 10})

    async def test_anonymous_admin_rejected(self):
        self.message.sender_chat = NS(id=-100)
        await self.admin.bind(self.update, self.context)
        self.bot.get_chat_member.assert_not_awaited()
        self.assertEqual(self.store.config_for(-100).topics, {})

    async def test_bot_requires_admin(self):
        self.bot.get_chat_member.side_effect = [NS(status="administrator"), NS(status="member")]
        await self.admin.bind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {})

    async def test_api_failure_denies_change(self):
        self.bot.get_chat_member.side_effect = BadRequest("unknown")
        await self.admin.bind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {})

    async def test_group_and_topic_required(self):
        self.message.chat.type = "private"
        await self.admin.bind(self.update, self.context)
        self.message.chat.type = "supergroup"
        self.message.is_topic_message = False
        await self.admin.bind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {})

    async def test_invalid_args(self):
        for args in [[], ["к", "ж"], ["help"], ["a b"]]:
            self.context.args = args
            await self.admin.bind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {})

    async def test_routes_only_current_group(self):
        self.store.bind(-100, "к", 12)
        self.store.bind(-200, "ж", 13)
        await self.admin.routes(self.update, self.context)
        self.message.reply_text.assert_awaited_once_with("/к → тема 12")

    async def test_revoked_admin_permissions_checked_again(self):
        await self.admin.bind(self.update, self.context)
        self.bot.get_chat_member.side_effect = [NS(status="member"), NS(status="administrator")]
        await self.admin.unbind(self.update, self.context)
        self.assertEqual(self.store.config_for(-100).topics, {"/к": 12})
