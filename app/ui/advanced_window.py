"""
AdvancedMainWindow - PersistentMainWindow plus the Phase 8 features, language handling,
the analytics dashboard and performance tuning.

Each feature starts inside its own try/except, so one broken feature never stops the others,
and never stops OPTIMUS from starting.
"""
import time
from datetime import date

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from app.brain.advanced_engine import AdvancedAIEngine
from app.config import (BRIEFING_ON_STARTUP, FEATURES, MULTILINGUAL_ENABLED, STT_IDLE_UNLOAD_MINUTES,
                        SYSTEM_PROMPT)
from app.features.analytics import AnalyticsFeature
from app.features.base import Services
from app.features.briefing import BriefingFeature, build_briefing
from app.features.coding import CodingFeature
from app.features.custom_workflows import WorkflowFeature
from app.features.file_search import FileSearchFeature
from app.features.history import HistoryFeature
from app.features.multilingual import LanguageFeature
from app.features.router import FeatureRouter
from app.features.state import load_state, save_state
from app.features.web import WebFeature
from app.ui.dashboard import DashboardDialog
from app.ui.persistent_window import PersistentMainWindow
from app.voice.languages import (LANG, detect_script_language, language_name, reply_instruction,
                                 voice_installed)
from app.voice.multilingual import MultilingualSTT, MultilingualTTS
from app.voice.styled import StyledTTS

# The order matters: broad rules (file search) go late so specific ones win.
# Workflows go last because they use the tools the other features register.
FEATURE_CLASSES = [("web", WebFeature), ("history", HistoryFeature), ("coding", CodingFeature),
                   ("briefing", BriefingFeature), ("language", LanguageFeature),
                   ("analytics", AnalyticsFeature), ("file_search", FileSearchFeature),
                   ("workflows", WorkflowFeature)]


class _NullSplitter:
    """Stops text from being read aloud (used for the list of web sources)."""
    def feed(self, text):
        return []

    def flush(self):
        return []


class AdvancedMainWindow(PersistentMainWindow):
    STT_CLASS = MultilingualSTT      # Used by MainWindow when it creates the speech engines
    TTS_CLASS = StyledTTS
    ui_action_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._features = []
        self._collector = None
        self._dashboard = None
        self._reply_language = "en"
        self._setup_performance()
        if self.storage is None:
            self.chat.add_message("error", "Advanced features need the database, which is unavailable right now.")
            return
        self._setup_features()
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._show_dashboard)
        QTimer.singleShot(2500, self._startup_briefing)

    # ------------------------------------------------------------------ features
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
                if isinstance(feature, AnalyticsFeature):
                    self._collector = feature.collector
            except Exception as exc:
                self.chat.add_message("error", f"The {name.replace('_', ' ')} feature could not start: {exc}")
        engine.attach(FeatureRouter(self._features), history_index,
                      conversation_id=lambda: self.current_conversation_id)
        self.engine = engine

        self.ui_action_requested.connect(self._on_ui_action)
        if self._collector is not None:                      # Light background sampling for history
            self._collect_timer = QTimer(self)
            self._collect_timer.setInterval(15_000)
            self._collect_timer.timeout.connect(self._collector.sample)
            self._collect_timer.start()

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

    def _on_ui_action(self, action: str):
        if action == "show_dashboard":
            self._show_dashboard()

    def _show_dashboard(self):
        if self._collector is None:
            self._flash_status("Analytics is switched off")
            return
        if self._dashboard is None:
            self._dashboard = DashboardDialog(self._collector, self)
        self._dashboard.show()
        self._dashboard.raise_()
        self._dashboard.activateWindow()

    # ------------------------------------------------------------------ language
    def _language_for(self, text: str, from_voice: bool) -> str:
        """Which language should this reply use?"""
        if not MULTILINGUAL_ENABLED:
            return "en"
        if LANG.preference != "auto":
            return LANG.preference
        if from_voice:
            return getattr(self.stt, "last_language", "en")   # What Whisper detected
        return detect_script_language(text) or "en"

    def _submit_to_ai(self, text: str, from_voice: bool):
        if self._busy:
            return
        language = self._language_for(text, from_voice)
        self._reply_language = language
        self.tts.set_language(language)
        self.engine.system_prompt = SYSTEM_PROMPT + reply_instruction(language)
        super()._submit_to_ai(text, from_voice)
        # Never read a language aloud with a voice that cannot speak it
        if self._busy and self._speak_reply and not voice_installed(language):
            self._speak_reply = False
            self._flash_status(f"No {language_name(language)} voice installed, showing text only")

    def _on_token(self, piece: str):
        """Do not read the web source list aloud."""
        if self._speak_reply and piece.startswith("\n\n**Sources**"):
            for sentence in self._splitter.flush():
                self.speech.speak(sentence)
            self._splitter = _NullSplitter()
        super()._on_token(piece)

    # ------------------------------------------------------------------ performance
    def _setup_performance(self):
        """Paint the orb less often and free the speech model when it is idle."""
        self._viz_steps = 2
        try:
            timer = self.visualizer._timer
            timer.timeout.disconnect(self.visualizer._tick)
            timer.timeout.connect(self._visualizer_step)
            self._tune_visualizer()
        except (RuntimeError, TypeError, AttributeError):
            self._viz_steps = 0                  # Could not retune: leave the orb as it was
        if STT_IDLE_UNLOAD_MINUTES:
            self._idle_timer = QTimer(self)
            self._idle_timer.setInterval(60_000)
            self._idle_timer.timeout.connect(self._free_idle_memory)
            self._idle_timer.start()

    def _visualizer_step(self):
        """One timer event advances the animation several steps, so the speed stays the same while painting less."""
        for _ in range(self._viz_steps):
            self.visualizer._tick()

    def _tune_visualizer(self):
        timer = self.visualizer._timer
        if self.isMinimized():
            timer.stop()                         # Nothing to see, so nothing to draw
            return
        self._viz_steps = 2 if self.isActiveWindow() else 6    # ~30 fps in front, ~10 fps behind
        timer.setInterval(16 * self._viz_steps)
        if self.visualizer._animated and not timer.isActive():
            timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, "_viz_steps", 0) and event.type() in (QEvent.ActivationChange, QEvent.WindowStateChange):
            self._tune_visualizer()

    def _free_idle_memory(self):
        """Unload the speech recognition model after a long pause (it reloads when you next speak)."""
        stt = self.stt
        if (hasattr(stt, "unload") and stt.is_loaded and not (self._recording or self._transcribing)
                and time.monotonic() - stt.last_used > STT_IDLE_UNLOAD_MINUTES * 60):
            stt.unload()