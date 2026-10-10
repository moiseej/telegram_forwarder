"""Send one clearly labelled test message through every configured route."""
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telegram import Bot
from forwarder.delivery import send_to_topic
from forwarder.errors import delivery_error_message
from forwarder.secrets import load_token
from forwarder.store import RouteStore


async def verify():
    store = RouteStore(Path(os.environ["FORWARDER_DB"]))
    with store.connect() as db:
        routes = list(db.execute("SELECT chat_id, code, topic_id FROM routes ORDER BY chat_id, code"))
    assert routes, "No configured routes"
    results = []
    async with Bot(load_token()) as bot:
        for chat_id, code, topic_id in routes:
            try:
                await send_to_topic(bot, chat_id, topic_id, f"✅ Проверка доставки {code}: маршрут работает.")
                results.append({"command": code, "topic_id": topic_id, "ok": True})
            except Exception as error:
                results.append({"command": code, "topic_id": topic_id, "ok": False,
                                "reason": delivery_error_message(error)})
    print(json.dumps(results, ensure_ascii=False))
    if not all(item["ok"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(verify())
