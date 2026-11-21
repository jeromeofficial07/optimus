"""
PersistentMainWindow - the existing MainWindow plus persistence.

  * saves every conversation and reloads it from the sidebar
  * swaps in the memory-aware engine and registers the memory/task/reminder tools
  * fires reminders (also ones that came due while OPTIMUS was closed)
  * keeps working, without saving, if the database cannot be used
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from app.brain.memory_engine import MemoryAIEngine
from app.storage.database import DatabaseError
from app.storage.repositories import Storage
from app.tools.productivity import register_productivity_tools
from app.ui.main_window import MainWindow

REMINDER_CHECK_MS = 10_000

MENU_QSS = ("QMenu { background: #0f1a3a; color: #e6ecff; border: 1px solid #1d4ed8; "
            "border-radius: 8px; padding: 6px; } QMenu::item { padding: 8px 18px; border-radius: 6px; } "
            "QMenu::item:selected { background: rgba(59,130,246,70); }")
DIALOG_QSS = ("QMessageBox { background: #0b1226; } QLabel { color: #e6ecff; font-size: 14px; } "
              "QPushButton { color: #e6ecff; background: rgba(255,255,255,24); "
              "border: 1px solid rgba(255,255,255,60); border-radius: 8px; padding: 8px 18px; "
              "min-width: 70px; } QPushButton:hover { background: rgba(59,130,246,90); }")


def _title_from(text: str) -> str:
    line = (text.strip().splitlines() or ["New conversation"])[0]
    return line if len(line) <= 48 else line[:45].rstrip() + "..."


class PersistentMainWindow(MainWindow):
    def __init__(self):
        super().__init__()  # Builds everything from phases 1-6
        self.storage: Storage | None = None
        self.current_conversation_id: int | None = None
        self._conversation_ids: list[int] = []   # Database ids, in the same order as the sidebar rows
        self._reply_buffer = ""
        self._db_warned = False
        self._init_storage()

    # ------------------------------------------------------------------ setup
    def _init_storage(self):
        try:
            self.storage = Storage()
        except DatabaseError as exc:
            self.storage = None
            self.sidebar.set_history([])
            self.chat.add_message("error", f"Saving is switched off for this session. {exc}")
            return

        if self.storage.db.recovered_from is not None:
            self.chat.add_message(
                "error",
                "The database file was damaged, so I moved it aside as "
                f"**{self.storage.db.recovered_from.name}** and started a fresh one.")

        register_productivity_tools(self.executor.registry, self.storage)
        self.engine = MemoryAIEngine(self.executor, self.storage)  # Replaces the plain engine

        self.sidebar.history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar.history.customContextMenuRequested.connect(self._history_menu)
        self._refresh_sidebar()

        self.chat.clear()
        self._show_welcome()  # Again, now that the name is known

        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(REMINDER_CHECK_MS)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()
        QTimer.singleShot(2000, lambda: self._check_reminders(startup=True))

    def _db(self, function, default=None):
        """Run a database operation. On failure warn once and carry on with a default value."""
        try:
            return function()
        except DatabaseError as exc:
            if not self._db_warned:
                self._db_warned = True
                self.chat.add_message("error", f"Memory problem: {exc} (I'll keep working without saving.)")
            return default

    # ------------------------------------------------------------------ welcome
    def _show_welcome(self):
        name = None
        if getattr(self, "storage", None) is not None:
            name = self._db(lambda: self.storage.memory.get("name"))
        greeting = f"Welcome back, {name}." if name else "Hello, I'm OPTIMUS."
        self.chat.add_message(
            "assistant",
            f"{greeting} I run entirely on this computer using **{self.engine.model}**. "
            "Type or **hold the microphone button** (or Ctrl+Space) to talk. "
            "I can open apps, find files, prepare your workspace, and I remember things between sessions. "
            "Try: *remember that my favorite color is blue*, *add task buy milk*, "
            "or *remind me in 10 minutes to stretch*.",
        )

    # ------------------------------------------------------------------ conversations
    def _refresh_sidebar(self, select_id: int | None = None):
        conversations = self._db(lambda: self.storage.conversations.list(), [])
        self._conversation_ids = [c["id"] for c in conversations]
        self.sidebar.set_history([c["title"] for c in conversations])
        if select_id in self._conversation_ids:
            self.sidebar.history.setCurrentRow(self._conversation_ids.index(select_id))

    def _new_chat(self):
        if not self._is_idle():
            return
        self._speech_stop()
        self.engine.reset()
        self.tool_context.last_search_results.clear()
        self.current_conversation_id = None   # A row is created when the first message is sent
        self._reply_buffer = ""
        self.sidebar.history.clearSelection()
        self.chat.clear()
        self._show_welcome()

    def _open_conversation(self, _title: str = ""):
        """A sidebar item was clicked: reload its messages and restore the AI's context."""
        if not self._is_idle() or self.storage is None:
            return
        row = self.sidebar.history.currentRow()
        if not 0 <= row < len(self._conversation_ids):
            return
        conversation_id = self._conversation_ids[row]
        messages = self._db(lambda: self.storage.messages.for_conversation(conversation_id))
        if messages is None:
            return
        self._speech_stop()
        self.chat.clear()
        for message in messages:
            self.chat.add_message(message["role"], message["content"], animate=False)
        self.engine.set_history(messages)
        self.current_conversation_id = conversation_id

    def _history_menu(self, position):
        item = self.sidebar.history.itemAt(position)
        if item is None or self.storage is None:
            return
        row = self.sidebar.history.row(item)
        menu = QMenu(self)
        menu.setStyleSheet(MENU_QSS)
        delete = menu.addAction("Delete conversation")
        if menu.exec(self.sidebar.history.viewport().mapToGlobal(position)) is delete:
            self._delete_conversation(self._conversation_ids[row])

    def _delete_conversation(self, conversation_id: int):
        if conversation_id == self.current_conversation_id and not self._is_idle():
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete conversation")
        box.setText("Delete this conversation and all of its messages?\nThis cannot be undone.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.setStyleSheet(DIALOG_QSS)
        if box.exec() != QMessageBox.Yes:
            return
        self._db(lambda: self.storage.conversations.delete(conversation_id))
        was_current = conversation_id == self.current_conversation_id
        self._refresh_sidebar(None if was_current else self.current_conversation_id)
        if was_current:
            self._new_chat()

    # ------------------------------------------------------------------ saving
    def _submit_to_ai(self, text: str, from_voice: bool):
        if self._busy:
            return
        self._reply_buffer = ""
        self._save_user_message(text)
        super()._submit_to_ai(text, from_voice)

    def _save_user_message(self, text: str):
        if self.storage is None:
            return

        def save():
            if self.current_conversation_id is None:
                self.current_conversation_id = self.storage.conversations.create(_title_from(text))
            self.storage.messages.add(self.current_conversation_id, "user", text)
            return True

        if self._db(save, False):
            self._refresh_sidebar(self.current_conversation_id)

    def _on_token(self, piece: str):
        self._reply_buffer += piece  # Collect the answer so it can be saved when it is complete
        super()._on_token(piece)

    def _save_assistant_message(self):
        text = self._reply_buffer.strip()
        self._reply_buffer = ""
        if self.storage is None or not text or self.current_conversation_id is None:
            return
        if self._db(lambda: self.storage.messages.add(self.current_conversation_id, "assistant", text), False) is not False:
            self._refresh_sidebar(self.current_conversation_id)

    def _on_reply_completed(self):
        self._save_assistant_message()
        super()._on_reply_completed()

    def _on_reply_failed(self, kind: str, message: str):
        self._save_assistant_message()  # Keep whatever part of the answer arrived
        super()._on_reply_failed(kind, message)

    # ------------------------------------------------------------------ reminders
    def _check_reminders(self, startup: bool = False):
        if self.storage is None:
            return
        due = self._db(lambda: self.storage.reminders.due(), [])
        if not due:
            return
        for reminder in due:
            self._db(lambda r=reminder: self.storage.reminders.mark_fired(r["id"]))

        if startup:
            lines = [f"- {r['text']} (was due {r['remind_at'][5:16]})" for r in due]
            self.chat.add_message("assistant", "**Reminders you missed while OPTIMUS was closed:**\n" + "\n".join(lines))
        elif len(due) == 1:
            self.chat.add_message("assistant", f"**Reminder:** {due[0]['text']}")
        else:
            self.chat.add_message("assistant", "**Reminders:**\n" + "\n".join(f"- {r['text']}" for r in due))

        self._flash_status("Reminder")
        QApplication.alert(self, 0)  # Flash the taskbar button
        if self._tts_ready and self._is_idle():
            self.speech.speak("Reminder. " + ". ".join(r["text"] for r in due))
            self._speech_end()

    # ------------------------------------------------------------------ closing
    def closeEvent(self, event):
        if hasattr(self, "_reminder_timer"):
            self._reminder_timer.stop()
        super().closeEvent(event)
        if self.storage is not None:
            self.storage.close()