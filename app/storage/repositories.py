"""
Repositories: small classes that hold the SQL for each table.
Storage is the single object the rest of the app uses.

All times are stored as local-time text "YYYY-MM-DD HH:MM:SS", which sorts correctly.
"""
import re
from datetime import datetime
from pathlib import Path

from app.config import DATABASE_PATH
from app.storage.database import Database

_STOP_WORDS = {"the", "and", "for", "you", "your", "what", "who", "how", "are", "was", "has",
               "have", "with", "that", "this", "can", "tell", "about", "my", "me", "is", "it"}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_text(moment) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S") if isinstance(moment, datetime) else str(moment)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in _STOP_WORDS}


class ConversationRepo:
    def __init__(self, db: Database, user_id: int):
        self.db, self.user_id = db, user_id

    def create(self, title: str) -> int:
        stamp = now_text()
        return self.db.execute(
            "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (self.user_id, title, stamp, stamp)).lastrowid

    def list(self, limit: int = 200) -> list[dict]:
        return self.db.rows(
            "SELECT id, title, updated_at FROM conversations WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC LIMIT ?", (self.user_id, limit))

    def delete(self, conversation_id: int):
        self.db.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?",
                        (conversation_id, self.user_id))  # Its messages go too (ON DELETE CASCADE)


class MessageRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, conversation_id: int, role: str, content: str) -> int:
        with self.db.transaction():  # Message and "last updated" change together
            new_id = self.db.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, now_text())).lastrowid
            self.db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                            (now_text(), conversation_id))
        return new_id

    def for_conversation(self, conversation_id: int) -> list[dict]:
        return self.db.rows(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,))


class TaskRepo:
    def __init__(self, db: Database, user_id: int):
        self.db, self.user_id = db, user_id

    def add(self, title: str, due_at=None, priority: int = 2) -> int:
        return self.db.execute(
            "INSERT INTO tasks (user_id, title, due_at, priority, created_at) VALUES (?, ?, ?, ?, ?)",
            (self.user_id, title, to_text(due_at) if due_at else None, priority, now_text())).lastrowid

    def open_tasks(self) -> list[dict]:
        """Open tasks in a stable order: dated ones first (soonest first), then the rest."""
        return self.db.rows(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'open' "
            "ORDER BY due_at IS NULL, due_at, priority, id", (self.user_id,))

    def complete(self, task_id: int):
        self.db.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                        (now_text(), task_id))

    def delete(self, task_id: int):
        self.db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, self.user_id))


class ReminderRepo:
    def __init__(self, db: Database, user_id: int):
        self.db, self.user_id = db, user_id

    def add(self, text: str, remind_at) -> int:
        return self.db.execute(
            "INSERT INTO reminders (user_id, text, remind_at, created_at) VALUES (?, ?, ?, ?)",
            (self.user_id, text, to_text(remind_at), now_text())).lastrowid

    def pending(self) -> list[dict]:
        return self.db.rows(
            "SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' "
            "ORDER BY remind_at, id", (self.user_id,))

    def due(self, now: str | None = None) -> list[dict]:
        """Pending reminders whose time has arrived (including ones missed while closed)."""
        return self.db.rows(
            "SELECT * FROM reminders WHERE user_id = ? AND status = 'pending' AND remind_at <= ? "
            "ORDER BY remind_at, id", (self.user_id, now or now_text()))

    def mark_fired(self, reminder_id: int):
        self.db.execute("UPDATE reminders SET status = 'fired', fired_at = ? WHERE id = ?",
                        (now_text(), reminder_id))

    def cancel(self, reminder_id: int):
        self.db.execute("UPDATE reminders SET status = 'cancelled' WHERE id = ?", (reminder_id,))


class MemoryRepo:
    def __init__(self, db: Database, user_id: int):
        self.db, self.user_id = db, user_id

    def remember(self, key: str, value: str, category: str = "general", source: str = "user"):
        """Save a fact. Saving the same key again replaces its value."""
        key = key.strip().lower()[:80]
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO user_memory (user_id, key, value, category, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, "
                "category = excluded.category, updated_at = excluded.updated_at",
                (self.user_id, key, value.strip(), category, source, now_text()))
            if key == "name":
                self.db.execute("UPDATE users SET name = ? WHERE id = ?", (value.strip(), self.user_id))

    def get(self, key: str) -> str | None:
        row = self.db.row("SELECT value FROM user_memory WHERE user_id = ? AND key = ?",
                          (self.user_id, key.strip().lower()))
        return row["value"] if row else None

    def forget(self, key: str) -> bool:
        return self.db.execute("DELETE FROM user_memory WHERE user_id = ? AND key = ?",
                               (self.user_id, key.strip().lower())).rowcount > 0

    def all(self) -> list[dict]:
        return self.db.rows("SELECT key, value, category, updated_at FROM user_memory "
                            "WHERE user_id = ? ORDER BY updated_at DESC", (self.user_id,))

    def find(self, text: str) -> list[dict]:
        """Memories that share words with the text, best match first."""
        wanted = _words(text)
        scored = []
        for memory in self.all():
            overlap = len(wanted & _words(memory["key"] + " " + memory["value"]))
            if overlap:
                scored.append((overlap, memory))
        return [m for _, m in sorted(scored, key=lambda item: item[0], reverse=True)]

    def relevant(self, text: str, limit: int = 8) -> list[dict]:
        """Memory retrieval: few memories -> all of them; many -> the best matches for this message."""
        memories = self.all()
        if len(memories) <= limit:
            return memories
        wanted = _words(text)

        def score(memory: dict) -> tuple:
            overlap = len(wanted & _words(memory["key"] + " " + memory["value"]))
            return (overlap * 3 + (5 if memory["category"] == "profile" else 0), memory["updated_at"])

        return sorted(memories, key=score, reverse=True)[:limit]


class Storage:
    """Owns the database and every repository."""

    def __init__(self, path: Path = DATABASE_PATH):
        self.db = Database(path)
        self.user_id = self._ensure_user()
        self.conversations = ConversationRepo(self.db, self.user_id)
        self.messages = MessageRepo(self.db)
        self.tasks = TaskRepo(self.db, self.user_id)
        self.reminders = ReminderRepo(self.db, self.user_id)
        self.memory = MemoryRepo(self.db, self.user_id)

    def _ensure_user(self) -> int:
        row = self.db.row("SELECT id FROM users ORDER BY id LIMIT 1")
        if row:
            return row["id"]
        return self.db.execute("INSERT INTO users (name, created_at) VALUES (?, ?)",
                               ("default", now_text())).lastrowid

    def close(self):
        self.db.close()