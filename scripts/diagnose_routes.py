"""Probe configured destinations with sendChatAction; sends no messages."""
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telegram import Bot
from telegram.error import TelegramError
from forwarder.errors import delivery_error_message
from forwarder.secrets import load_token
from forwarder.store import RouteStore


async def diagnose():
    store = RouteStore(Path(os.environ["FORWARDER_DB"]))
    with store.connect() as db:
        routes = list(db.execute("SELECT chat_id, code, topic_id FROM routes ORDER BY chat_id, code"))
    assert routes, "No configured routes"
    results = []
    async with Bot(load_token()) as bot:
        chats = {}
        for chat_id, code, topic_id in routes:
            if chat_id not in chats:
                member = await bot.get_chat_member(chat_id, bot.id)
                chats[chat_id] = {"bot_status": member.status,
                                  "can_manage_topics": bool(getattr(member, "can_manage_topics", False))}
            try:
                await bot.send_chat_action(chat_id=chat_id, message_thread_id=topic_id, action="typing")
                results.append({"command": code, "topic_id": topic_id, "ok": True})
            except TelegramError as error:
                results.append({"command": code, "topic_id": topic_id, "ok": False,
                                "reason": delivery_error_message(error)})
    print(json.dumps({"chats": list(chats.values()), "routes": results}, ensure_ascii=False))
    if not all(item["ok"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(diagnose())
