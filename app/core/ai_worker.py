"""
Background workers.

Qt windows freeze if slow work (like waiting for an AI model) runs on the GUI
thread, so the work runs in a QThread and reports back using signals.

ReplyWorker       - sends one user message, streams the answer, runs approved actions
HealthCheckWorker - checks Ollama and warms up the model at startup
"""
import threading

from PySide6.QtCore import QThread, Signal

from app.agent.executor import ConfirmationRequest, ToolCallbacks
from app.brain.ai_engine import AIEngine, AIEngineError
from app.config import CONFIRMATION_TIMEOUT


class ReplyWorker(QThread):
    token = Signal(str)                          # A new piece of the answer arrived
    completed = Signal()                         # The answer finished normally
    failed = Signal(str, str)                    # (error kind, friendly message)
    tool_started = Signal(str)                   # "Opening Notepad..."
    tool_finished = Signal(bool, str)            # (success, message)
    confirmation_requested = Signal(str, str, str)  # (title, description, risk)

    def __init__(self, engine: AIEngine, user_text: str, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._text = user_text
        self._cancelled = False
        self._confirm_event = threading.Event()
        self._confirm_answer = False

    # ----- called from the GUI thread
    def cancel(self):
        """Stop at the next piece of output (also releases a waiting permission prompt)."""
        self._cancelled = True
        self.answer_confirmation(False)

    def answer_confirmation(self, allowed: bool):
        """The user clicked Allow or Deny."""
        self._confirm_answer = allowed
        self._confirm_event.set()

    # ----- runs on the worker thread
    def _ask_permission(self, request: ConfirmationRequest) -> bool:
        """Show the permission card in the GUI and wait here until the user answers."""
        self._confirm_event.clear()
        self._confirm_answer = False
        self.confirmation_requested.emit(request.title, request.description, request.risk.value)
        self._confirm_event.wait(CONFIRMATION_TIMEOUT + 5)  # The card auto-denies before this ends
        return self._confirm_answer and not self._cancelled

    def run(self):
        callbacks = ToolCallbacks(
            confirm=self._ask_permission,
            on_start=self.tool_started.emit,
            on_result=lambda result: self.tool_finished.emit(result.ok, result.message),
        )
        stream = self._engine.stream_reply(self._text, callbacks)
        try:
            for piece in stream:
                if self._cancelled:
                    break
                self.token.emit(piece)
        except AIEngineError as err:
            self.failed.emit(err.kind, err.message)
            return
        except Exception as exc:  # Safety net so a bug never kills the thread silently
            self.failed.emit("unknown", f"Unexpected error: {exc}")
            return
        finally:
            stream.close()
        if not self._cancelled:
            self.completed.emit()


class HealthCheckWorker(QThread):
    loading = Signal()           # Server and model found; now loading the model into RAM
    checked = Signal(str, str)   # (kind, message). kind == "ok" means ready

    def __init__(self, engine: AIEngine, parent=None):
        super().__init__(parent)
        self._engine = engine

    def run(self):
        kind, message = self._engine.check_connection()
        if kind == "ok":
            self.loading.emit()
            self._engine.warm_up()
        self.checked.emit(kind, message)