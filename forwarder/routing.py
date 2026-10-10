"""Parse commands without Telegram or network dependencies."""
from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class Route:
    command: str
    topic_id: int
    text: str


def parse_command(source: str, topics: Mapping[str, int], bot_username: str) -> Route | None:
    parts = source.strip().split(maxsplit=1)
    if not parts:
        return None
    command, separator, recipient = parts[0].lower().partition("@")
    if separator and recipient != bot_username.lower():
        return None
    if command not in topics:
        return None
    return Route(command, topics[command], parts[1].strip() if len(parts) > 1 else "")


def format_message(author: str, text: str) -> str:
    return f"{author}\n\n{text}" if text else author
