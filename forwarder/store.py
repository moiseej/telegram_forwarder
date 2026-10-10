"""Persistent, group-isolated routes with transactional updates."""
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager

from .config import Config

RESERVED = {"bind", "unbind", "routes", "start", "help"}


def normalize_code(code: str) -> str:
    code = code.strip().removeprefix("/").lower()
    if not re.fullmatch(r"\w{1,32}", code) or code in RESERVED:
        raise ValueError("Код: 1–32 буквы, цифры или _, кроме bind/unbind/routes/start/help.")
    return "/" + code


class RouteStore:
    def __init__(self, path: Path, legacy: Config | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS routes (chat_id INTEGER, code TEXT, topic_id INTEGER NOT NULL, PRIMARY KEY(chat_id, code))")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY)")
            if not db.execute("SELECT 1 FROM metadata WHERE key='initialized'").fetchone():
                if legacy:
                    for code, topic in legacy.topics.items():
                        db.execute("INSERT INTO routes VALUES (?, ?, ?)", (legacy.chat_id, normalize_code(code), topic))
                db.execute("INSERT INTO metadata VALUES ('initialized')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def config_for(self, chat_id: int) -> Config:
        with self.connect() as db:
            topics = dict(db.execute("SELECT code, topic_id FROM routes WHERE chat_id=? ORDER BY code", (chat_id,)))
        return Config(chat_id, topics)

    def bind(self, chat_id: int, code: str, topic_id: int) -> str:
        code = normalize_code(code)
        if type(chat_id) is not int or chat_id >= 0 or type(topic_id) is not int or topic_id <= 0:
            raise ValueError("Нужна группа и существующая тема.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("SELECT 1 FROM routes WHERE chat_id=? AND code=?", (chat_id, code)).fetchone()
            count = db.execute("SELECT COUNT(*) FROM routes WHERE chat_id=?", (chat_id,)).fetchone()[0]
            if not exists and count >= 50:
                raise ValueError("Лимит: 50 команд на группу. Удалите ненужную через /unbind.")
            db.execute("INSERT INTO routes VALUES (?, ?, ?) ON CONFLICT(chat_id, code) DO UPDATE SET topic_id=excluded.topic_id", (chat_id, code, topic_id))
        return code

    def unbind(self, chat_id: int, code: str) -> bool:
        with self.connect() as db:
            result = db.execute("DELETE FROM routes WHERE chat_id=? AND code=?", (chat_id, normalize_code(code)))
            return result.rowcount > 0
