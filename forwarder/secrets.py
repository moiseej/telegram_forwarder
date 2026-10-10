"""Load credentials at runtime, never from the image or command line."""
import os
from pathlib import Path


def load_token() -> str:
    path = os.getenv("BOT_TOKEN_FILE")
    token = Path(path).read_text(encoding="utf-8").strip() if path else (
        os.getenv("TOPIC_FORWARD_BOT_TOKEN") or os.getenv("BOT_TOKEN") or ""
    ).strip()
    if not token:
        raise RuntimeError("Set BOT_TOKEN_FILE or TOPIC_FORWARD_BOT_TOKEN")
    return token
