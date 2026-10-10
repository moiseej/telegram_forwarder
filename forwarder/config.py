"""Load and validate local routing configuration."""
from dataclasses import dataclass
from pathlib import Path
import re

import yaml


@dataclass(frozen=True)
class Config:
    chat_id: int
    topics: dict[str, int]


def load_config(path: Path) -> Config:
    with path.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must contain a mapping")
    chat_id = raw.get("chat_id")
    if type(chat_id) is not int or chat_id >= 0:
        raise ValueError("chat_id must be a negative integer")
    source = raw.get("topics")
    if not isinstance(source, dict) or not source:
        raise ValueError("topics must be a non-empty mapping")
    topics = {}
    for code, topic_id in source.items():
        command = str(code).strip().lstrip("/").lower()
        if not re.fullmatch(r"\w+", command):
            raise ValueError("Topic commands must contain letters, digits or underscores")
        command = "/" + command
        if command in topics:
            raise ValueError(f"Duplicate command: {command}")
        if type(topic_id) is not int or topic_id <= 0:
            raise ValueError(f"Topic ID for {command} must be a positive integer")
        topics[command] = topic_id
    return Config(chat_id, topics)
