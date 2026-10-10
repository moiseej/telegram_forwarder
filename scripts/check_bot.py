"""Read-only live Telegram connectivity check. Never print URLs or credentials."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telegram import Bot
from forwarder.secrets import load_token


async def check():
    async with Bot(load_token()) as bot:
        me = await bot.get_me()
        webhook = await bot.get_webhook_info()
        assert me.is_bot and me.username, "Expected bot identity"
        assert not webhook.url, "Webhook active: do not start polling until its owner disables it"
        print(json.dumps({"ok": True, "username": me.username, "can_join_groups": me.can_join_groups,
                          "reads_all_group_messages": me.can_read_all_group_messages, "webhook_active": False}))


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"Bot check failed ({type(error).__name__}); check credentials/network/webhook settings.", file=sys.stderr)
        sys.exit(1)
