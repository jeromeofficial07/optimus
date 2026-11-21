"""
Database - one SQLite connection that every thread can use safely.

  * a lock serialises access (the GUI and the worker threads both read and write)
  * WAL mode and foreign keys are switched on
  * the schema is versioned with PRAGMA user_version, ready for future upgrades
  * a damaged database file is moved aside and a fresh one is created
  * every sqlite3 error is converted to a DatabaseError with a readable message
"""
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import DATABASE_PATH

SCHEMA_V1 = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, id);
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    due_at TEXT,
    priority INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'fired', 'cancelled')),
    created_at TEXT NOT NULL,
    fired_at TEXT
);
CREATE INDEX idx_reminders_due ON reminders(status, remind_at);
CREATE TABLE user_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    source TEXT NOT NULL DEFAULT 'user',
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, key)
);
"""


class DatabaseError(Exception):
    """Any database problem. The message is safe to show to the user."""


@dataclass
class Result:
    lastrowid: int   # Id of the inserted row
    rowcount: int    # How many rows an UPDATE or DELETE changed


class Database:
    def __init__(self, path: Path = DATABASE_PATH):
        self.path = Path(path)
        self.recovered_from: Path | None = None  # Set if a damaged file was moved aside
        self._lock = threading.RLock()
        self._depth = 0                           # Nesting level of transaction()
        self._conn = self._open()

    # ------------------------------------------------------------ opening
    def _open(self) -> sqlite3.Connection:
        try:
            return self._connect()
        except sqlite3.DatabaseError as exc:  # Also covers "locked" errors, so check the text
            text = str(exc).lower()
            if "not a database" in text or "malformed" in text or "corrupt" in text:
                self._quarantine()
                try:
                    return self._connect()
                except (sqlite3.Error, OSError) as again:
                    raise DatabaseError(f"Could not create a new database: {again}") from again
            raise DatabaseError(f"Could not open the database: {exc}") from exc
        except (sqlite3.Error, OSError) as exc:
            raise DatabaseError(f"Could not open the database: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False is safe because every call goes through self._lock
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("database disk image is malformed")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._migrate(conn)
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _migrate(conn: sqlite3.Connection):
        """Bring the database up to the current schema version (all or nothing)."""
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.executescript("BEGIN;" + SCHEMA_V1 + "PRAGMA user_version = 1; COMMIT;")
        # Future upgrades go here:  if version < 2: ...

    def _quarantine(self):
        """Move a damaged database aside so a new one can be created."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.path.with_name(f"{self.path.stem}_damaged_{stamp}{self.path.suffix}")
        try:
            shutil.move(str(self.path), str(target))
            for suffix in ("-wal", "-shm"):
                side = Path(str(self.path) + suffix)
                if side.exists():
                    side.unlink()
        except OSError as exc:
            raise DatabaseError(f"The database file is damaged and could not be moved aside: {exc}") from exc
        self.recovered_from = target

    # ------------------------------------------------------------ queries
    def execute(self, sql: str, params=()) -> Result:
        """Run INSERT / UPDATE / DELETE. Commits immediately unless inside transaction()."""
        with self._lock:
            try:
                cursor = self._conn.execute(sql, params)
                if self._depth == 0:
                    self._conn.commit()
                return Result(cursor.lastrowid, cursor.rowcount)
            except sqlite3.Error as exc:
                if self._depth == 0:
                    self._conn.rollback()
                raise DatabaseError(f"Database error: {exc}") from exc

    def rows(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            try:
                return [dict(row) for row in self._conn.execute(sql, params).fetchall()]
            except sqlite3.Error as exc:
                raise DatabaseError(f"Database error: {exc}") from exc

    def row(self, sql: str, params=()) -> dict | None:
        found = self.rows(sql, params)
        return found[0] if found else None

    @contextmanager
    def transaction(self):
        """Group several writes so they all succeed or none do."""
        with self._lock:
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self._conn.rollback()
                raise
            else:
                self._depth -= 1
                if self._depth == 0:
                    try:
                        self._conn.commit()
                    except sqlite3.Error as exc:
                        self._conn.rollback()
                        raise DatabaseError(f"Database error: {exc}") from exc

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass