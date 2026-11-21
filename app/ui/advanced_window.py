"""
AdvancedMainWindow - PersistentMainWindow plus the Phase 8 features.

Each feature starts inside its own try/except, so one broken feature never stops the others,
and never stops OPTIMUS from starting.
"""
from datetime import date

from PySide6.QtCore import QTimer, Signal

from app.brain.advanced_engine import AdvancedAIEngine
from app.config import BRIEFING_ON_STARTUP, FEATURES
from app.features.base import Services
from app.features.briefing import BriefingFeature, build_briefing
from app.features.coding import CodingFeature
from app.features.file_search import FileSearchFeature
from app.features.history import HistoryFeature
from app.features.router import FeatureRouter
from app.features.state import load_state, save_state
from app.features.web import WebFeature
from app.ui.persistent_window import PersistentMainWindow

# The order matters: broad rules (file search) go last so specific ones win
FEATURE_CLASSES = [("web", WebFeature), ("history", HistoryFeature), ("coding", CodingFeature),
                   ("briefing", BriefingFeature), ("file_search", FileSearchFeature)]


class _NullSplitter:
    """Stops text from being read aloud (used for the list of web sources)."""
    def feed(self, text):
        return []

    def flush(self):
        return []


class AdvancedMainWindow(PersistentMainWindow):
    ui_action_requested = Signal(str)   # Reserved for the dashboard in part 8B

    def __init__(self):
        super().__init__()
        self._features = []
        if self.storage is None:
            self.chat.add_message("error", "Advanced features need the database, which is unavailable right now.")
            return
        self._setup_features()
        QTimer.singleShot(2500, self._startup_briefing)

    def _setup_features(self):
        engine = AdvancedAIEngine(self.executor, self.storage)
        services = Services(storage=self.storage, registry=self.executor.registry,
                            controller=engine._agent.controller, context=self.tool_context,
                            llm=engine, ui=self.ui_action_requested.emit)
        history_index = None
        for name, feature_class in FEATURE_CLASSES:
            if not FEATURES.get(name, True):
                continue
            try:
                feature = feature_class(services)
                feature.register_tools()
                self._features.append(feature)
                history_index = getattr(feature, "index", history_index)
            except Exception as exc:
                self.chat.add_message("error", f"The {name.replace('_', ' ')} feature could not start: {exc}")
        engine.attach(FeatureRouter(self._features), history_index,
                      conversation_id=lambda: self.current_conversation_id)
        self.engine = engine

    def _startup_briefing(self):
        """Show the daily briefing once per day, when OPTIMUS starts."""
        if not BRIEFING_ON_STARTUP or not any(isinstance(f, BriefingFeature) for f in self._features):
            return
        state, today = load_state(), date.today().isoformat()
        if state.get("last_briefing") == today:
            return
        text = self._db(lambda: build_briefing(self.storage))
        if text:
            state["last_briefing"] = today
            save_state(state)
            self.chat.add_message("assistant", text)

    def _on_token(self, piece: str):
        """Do not read the web source list aloud."""
        if self._speak_reply and piece.startswith("\n\n**Sources**"):
            for sentence in self._splitter.flush():
                self.speech.speak(sentence)
            self._splitter = _NullSplitter()
        super()._on_token(piece)