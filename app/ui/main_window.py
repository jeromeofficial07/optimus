"""
MainWindow - assembles every component and wires them together.

Phase 5 adds computer automation. When the AI asks for an action:
  ToolExecutor validates it -> a permission card appears if it is sensitive
  -> the action runs -> a green/red chip shows the outcome -> the AI explains it.
"""
import sys

import numpy as np
from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QVBoxLayout

from app.agent.executor import ToolExecutor
from app.agent.path_guard import PathGuard
from app.agent.registry import ToolContext
from app.brain.ai_engine import AIEngine
from app.config import (APP_NAME, MIN_RECORD_SECONDS, SAMPLE_RATE, SEARCH_DIRECTORIES,
                        SILENCE_RMS_THRESHOLD)
from app.core.ai_worker import HealthCheckWorker, ReplyWorker
from app.core.voice_workers import MicRecorder, SpeechWorker, TranscribeWorker, VoiceInitWorker
from app.tools.builtin import build_default_registry
from app.ui.agent_widgets import ActionChip, ConfirmationCard
from app.ui.chat_widgets import ChatView
from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.icon_button import IconButton
from app.ui.input_bar import InputBar
from app.ui.settings_panel import SettingsPanel
from app.ui.sidebar import Sidebar
from app.ui.status_indicator import StatusIndicator
from app.ui.visualizer import AIVisualizer
from app.voice.stt_engine import STTEngine
from app.voice.tts_engine import SentenceSplitter, TTSEngine

SETTINGS_WIDTH = 330
SETTINGS_MARGIN = 18
NARROW_BREAKPOINT = 1000  # Below this width the sidebar auto-hides


class MainWindow(QMainWindow):
    # Lets worker threads (for example the screenshot tool) ask the GUI to hide/show the window
        # Subclasses can swap in different speech engines
    STT_CLASS = STTEngine
    TTS_CLASS = TTSEngine

    window_visibility_requested = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}")
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        # ----- interface state -----
        self._narrow = False
        self._settings_open = False
        self._title_bar_done = False

        # ----- automation: tools, safety checks and the AI engine -----
        self.tool_context = ToolContext(
            guard=PathGuard(SEARCH_DIRECTORIES),
            set_window_hidden=self.window_visibility_requested.emit,
        )
        self.executor = ToolExecutor(build_default_registry(), self.tool_context)
        self.engine = AIEngine(executor=self.executor)
        self._engine_state = "checking"   # "checking", "ok" or "offline"
        self._busy = False                # True while a reply is being generated
        self._current_bubble = None       # The assistant bubble being filled in
        self._reply_worker = None         # The running ReplyWorker (for permission answers)
        self._pending_card = None         # A permission card waiting for Allow/Deny

        # ----- voice state -----
        self.stt = self.STT_CLASS()
        self.tts = self.TTS_CLASS()
        self.speech = SpeechWorker(self.tts, parent=self)
        self._voice_loading = True
        self._stt_ready = False
        self._tts_ready = False
        self._stt_error = ""
        self._recording = False
        self._recorder = None
        self._ptt_key_down = False
        self._transcribing = False
        self._speak_reply = False
        self._voice_replies_on = False
        self._splitter = SentenceSplitter()
        self._speech_ends_pending = 0

        self._threads = set()             # Every running worker thread

        self.central = BackgroundWidget()
        self.setCentralWidget(self.central)

        self._build_ui()
        self._connect_signals()
        QApplication.instance().installEventFilter(self)  # Needed for Ctrl+Space push-to-talk

        self._show_welcome()
        self._set_state("idle")
        self.speech.start()
        self._start_health_check()
        self._start_voice_init()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        """Create all widgets and arrange them in layouts."""
        root = QHBoxLayout(self.central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        column = QVBoxLayout()
        column.setSpacing(14)
        root.addLayout(column, 1)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.menu_button = IconButton("menu", size=40, tooltip="Show / hide sidebar")
        self.status = StatusIndicator()
        self.settings_button = IconButton("gear", size=40, tooltip="Settings")
        top.addWidget(self.menu_button)
        top.addWidget(self.status)
        top.addStretch(1)
        top.addWidget(self.settings_button)
        column.addLayout(top)

        self.visualizer_panel = GlassPanel(radius=26, tint=0.45)
        self.visualizer_panel.setMinimumHeight(170)
        viz_layout = QVBoxLayout(self.visualizer_panel)
        viz_layout.setContentsMargins(8, 8, 8, 8)
        self.visualizer = AIVisualizer()
        viz_layout.addWidget(self.visualizer)
        column.addWidget(self.visualizer_panel, 2)

        self.chat_panel = GlassPanel(radius=26, tint=0.5)
        self.chat_panel.setMinimumHeight(220)
        chat_layout = QVBoxLayout(self.chat_panel)
        chat_layout.setContentsMargins(6, 6, 6, 6)
        self.chat = ChatView()
        chat_layout.addWidget(self.chat)
        column.addWidget(self.chat_panel, 5)

        self.input_bar = InputBar()
        column.addWidget(self.input_bar)

        self.settings = SettingsPanel(self.central)
        self.settings.hide()

        self._settings_anim = QPropertyAnimation(self.settings, b"geometry", self)
        self._settings_anim.setDuration(340)
        self._settings_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._settings_anim.finished.connect(self._on_settings_anim_finished)

    def _connect_signals(self):
        """Connect widget signals to the methods that handle them."""
        self.sidebar.new_chat_requested.connect(self._new_chat)
        self.sidebar.conversation_selected.connect(self._open_conversation)

        self.input_bar.message_submitted.connect(self._on_user_message)
        self.input_bar.mic_pressed.connect(self._start_recording)
        self.input_bar.mic_released.connect(self._stop_recording)

        self.menu_button.clicked.connect(self._toggle_sidebar)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.settings.closed.connect(self._close_settings)

        self.settings.animations_toggled.connect(self.visualizer.set_animated)
        self.settings.timestamps_toggled.connect(self.chat.set_timestamps_visible)
        self.settings.font_size_changed.connect(self.chat.set_font_size)
        self.settings.voice_replies_toggled.connect(self._on_voice_replies_toggled)

        self.speech.speaking_started.connect(self._on_speaking_started)
        self.speech.speaking_finished.connect(self._on_speaking_finished)
        self.speech.failed.connect(self._on_speech_failed)

        self.window_visibility_requested.connect(self._set_window_hidden)
        self.central.resized.connect(self._on_central_resized)

        escape = QShortcut(QKeySequence("Esc"), self)
        escape.activated.connect(self._on_escape)

    # ------------------------------------------------------------------ threads
    def _start_thread(self, thread):
        """Remember a worker thread, clean it up when it finishes, and start it."""
        self._threads.add(thread)
        thread.finished.connect(self._on_thread_finished)
        thread.start()

    def _on_thread_finished(self):
        thread = self.sender()
        self._threads.discard(thread)
        if thread is self._recorder:
            self._recorder = None
        if thread is self._reply_worker:
            self._reply_worker = None
        if thread is not None:
            thread.deleteLater()

    def closeEvent(self, event):
        """Stop every background thread before the window closes, so Python exits cleanly."""
        if self._recorder is not None:
            self._recorder.stop_recording()
        for worker in list(self._threads):
            try:
                if hasattr(worker, "cancel"):
                    worker.cancel()
                if not worker.wait(3000):    # Give it 3 seconds to stop politely
                    worker.terminate()       # Last resort at shutdown only
                    worker.wait(1000)
            except RuntimeError:
                pass  # The thread object was already deleted
        self.speech.shutdown()
        if not self.speech.wait(3000):
            self.speech.terminate()
            self.speech.wait(1000)
        super().closeEvent(event)

    # ------------------------------------------------------------------ state
    def _is_idle(self) -> bool:
        return not (self._busy or self._recording or self._transcribing)

    def _rest_state(self) -> str:
        return "speaking" if self._speech_ends_pending > 0 else "idle"

    def _set_state(self, state: str, text: str | None = None):
        """Update the visualizer AND the status indicator together."""
        self.visualizer.set_state(state)
        if state == "idle":
            key, default = {
                "checking": ("busy", "Connecting to AI..."),
                "ok": ("ready", "AI online"),
                "offline": ("offline", "AI offline"),
            }[self._engine_state]
        else:
            key, default = {
                "listening": ("listening", "Listening..."),
                "thinking": ("busy", "Thinking..."),
                "speaking": ("busy", "Speaking..."),
            }[state]
        self.status.set_status(key, text or default)

    def _flash_status(self, message: str):
        """Show a short message in the status area for a moment, then restore it."""
        self.status.set_status("ready", message)
        self.visualizer.set_state(self._rest_state())
        QTimer.singleShot(2500, self._restore_status)

    def _restore_status(self):
        if self._is_idle():
            self._set_state(self._rest_state())

    # ------------------------------------------------------------------ startup checks
    def _start_health_check(self):
        worker = HealthCheckWorker(self.engine, parent=self)
        worker.loading.connect(self._on_model_loading)
        worker.checked.connect(self._on_health_checked)
        self._start_thread(worker)

    def _on_model_loading(self):
        self.status.set_status("busy", "Loading model...")
        self.visualizer.set_state("thinking")

    def _on_health_checked(self, kind: str, message: str):
        if kind == "ok":
            self._engine_state = "ok"
        else:
            self._engine_state = "offline"
            self.chat.add_message("error", message)
        if self._is_idle():
            self._set_state(self._rest_state())

    def _start_voice_init(self):
        worker = VoiceInitWorker(self.stt, self.tts, parent=self)
        worker.loaded.connect(self._on_voice_loaded)
        self._start_thread(worker)

    def _on_voice_loaded(self, stt_error: str, tts_error: str):
        self._voice_loading = False
        self._stt_ready = not stt_error
        self._tts_ready = not tts_error
        self._stt_error = stt_error
        for message in (stt_error, tts_error):
            if message:
                self.chat.add_message("error", message)
        if self._stt_ready and self._tts_ready and self._is_idle():
            self._flash_status("Voice ready")

    # ------------------------------------------------------------------ chat flow
    def _show_welcome(self):
        self.chat.add_message(
            "assistant",
            f"Hello, I'm OPTIMUS. I run entirely on this computer using **{self.engine.model}**. "
            "Type or **hold the microphone button** (or Ctrl+Space) and talk to me. "
            "I can open apps, find files, take screenshots, check your CPU, memory and battery, "
            "and lock the PC. Try: *open Notepad*, *find my resume* or *how much battery do I have?*",
        )

    def _new_chat(self):
        if not self._is_idle():
            return  # Don't wipe the chat in the middle of something
        self._speech_stop()
        self.engine.reset()
        self.tool_context.last_search_results.clear()
        self.chat.clear()
        self.sidebar.add_conversation("New conversation")
        self._show_welcome()

    def _open_conversation(self, title: str):
        if not self._is_idle():
            return
        self._speech_stop()
        self.engine.reset()
        self.chat.clear()
        self.chat.add_message(
            "assistant",
            f"Placeholder: the conversation '{title}' will be loaded from the "
            "database once persistent memory is added.",
        )

    def _on_user_message(self, text: str):
        """A message typed into the text field."""
        self._submit_to_ai(text, from_voice=False)

    def _submit_to_ai(self, text: str, from_voice: bool):
        """Send text (typed or transcribed) to the AI and start streaming the answer."""
        if self._busy:
            return
        self._busy = True
        self._current_bubble = None
        self._speak_reply = self._tts_ready and (from_voice or self._voice_replies_on)
        if self._speak_reply:
            self._splitter = SentenceSplitter()
        self._speech_stop()

        self.chat.add_message("user", text)
        self.input_bar.set_busy(True)
        self._set_state("thinking")
        self.chat.show_typing()

        worker = ReplyWorker(self.engine, text, parent=self)
        worker.token.connect(self._on_token)
        worker.completed.connect(self._on_reply_completed)
        worker.failed.connect(self._on_reply_failed)
        worker.tool_started.connect(self._on_tool_started)
        worker.tool_finished.connect(self._on_tool_finished)
        worker.confirmation_requested.connect(self._on_confirmation_requested)
        self._reply_worker = worker
        self._start_thread(worker)

    def _on_token(self, piece: str):
        """A piece of the answer arrived. The first piece creates the bubble."""
        if self._current_bubble is None:
            self.chat.hide_typing()
            self._set_state("speaking", "Speaking..." if self._speak_reply else "Responding...")
            self._current_bubble = self.chat.add_message("assistant", piece, animate=False)
        else:
            self.chat.append_to_bubble(self._current_bubble, piece)
        if self._speak_reply:
            for sentence in self._splitter.feed(piece):
                self.speech.speak(sentence)

    def _on_reply_completed(self):
        if self._current_bubble is None:
            self.chat.hide_typing()
            self.chat.add_message("error", "The model returned an empty reply. Please try again.")
        if self._speak_reply:
            for sentence in self._splitter.flush():
                self.speech.speak(sentence)
            self._speech_end()
        self._engine_state = "ok"
        self._finish_generation()

    def _on_reply_failed(self, kind: str, message: str):
        self.chat.hide_typing()
        self.chat.add_message("error", message)
        if self._speak_reply:
            self._speech_end()
        if kind in ("offline", "no_model"):
            self._engine_state = "offline"
        self._finish_generation()

    def _finish_generation(self):
        """Back to normal: unlock the input and return to the resting state."""
        self._busy = False
        self._speak_reply = False
        self._current_bubble = None
        self.input_bar.set_busy(False)
        self._set_state(self._rest_state())

    # ------------------------------------------------------------------ automation events
    def _on_tool_started(self, description: str):
        """An approved action is starting: show what it is."""
        self.status.set_status("busy", description)
        self.visualizer.set_state("thinking")

    def _on_tool_finished(self, ok: bool, message: str):
        """An action finished (or was rejected): show a green or red chip in the chat."""
        first_line = (message.splitlines() or [""])[0]
        self.chat.add_widget(ActionChip(ok, first_line[:160]))
        self.status.set_status("busy", "Thinking...")

    def _on_confirmation_requested(self, title: str, description: str, risk: str):
        """A sensitive action needs permission: show the Allow / Deny card."""
        card = ConfirmationCard(title, description, risk)
        card.decided.connect(self._on_confirmation_decided)
        self._pending_card = card
        self.chat.add_widget(card)
        self.status.set_status("busy", "Waiting for your permission")

    def _on_confirmation_decided(self, allowed: bool):
        self._pending_card = None
        if self._reply_worker is not None:
            self._reply_worker.answer_confirmation(allowed)  # Wakes the worker thread
        self.status.set_status("busy", "Thinking...")

    def _set_window_hidden(self, hidden: bool):
        """Minimise or restore the window (used so screenshots don't include OPTIMUS)."""
        if hidden:
            self.showMinimized()
        else:
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
            self.show()
            self.raise_()
            self.activateWindow()

    # ------------------------------------------------------------------ push-to-talk
    def eventFilter(self, obj, event):
        """Watches every key press in the app so Ctrl+Space works as hold-to-talk."""
        etype = event.type()
        if etype == QEvent.KeyPress:
            if (event.key() == Qt.Key_Space and bool(event.modifiers() & Qt.ControlModifier)
                    and self.isActiveWindow()):
                if not event.isAutoRepeat() and not self._ptt_key_down:
                    self._ptt_key_down = True
                    self._start_recording()
                return True
        elif etype == QEvent.KeyRelease:
            if self._ptt_key_down and event.key() in (Qt.Key_Space, Qt.Key_Control):
                if not event.isAutoRepeat():
                    self._ptt_key_down = False
                    self._stop_recording()
                return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        """If the window loses focus while the keys are held, stop recording."""
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow() and self._ptt_key_down:
            self._ptt_key_down = False
            self._stop_recording()
        super().changeEvent(event)

    def _start_recording(self):
        """Mic button pressed or Ctrl+Space pushed down: start capturing."""
        if self._recording or self._transcribing:
            return
        if self._busy:
            self._flash_status("Please wait for the current answer")
            return
        if self._voice_loading:
            self._flash_status("Voice is still loading...")
            return
        if not self._stt_ready:
            self.chat.add_message("error", self._stt_error or "Voice input is not available.")
            return

        self._speech_stop()
        self._recording = True
        recorder = MicRecorder(parent=self)
        recorder.level.connect(self.input_bar.set_level)
        recorder.recorded.connect(self._on_recorded)
        recorder.failed.connect(self._on_recorder_failed)
        self._recorder = recorder
        self.input_bar.set_mic_state("recording")
        self._set_state("listening")
        self._start_thread(recorder)

    def _stop_recording(self):
        """Mic button / Ctrl+Space released: stop capturing and wait for the audio."""
        if not self._recording:
            return
        self._recording = False
        self._transcribing = True
        if self._recorder is not None:
            self._recorder.stop_recording()
        self.input_bar.set_mic_state("processing")
        self.input_bar.set_busy(True)
        self.status.set_status("busy", "Processing audio...")
        self.visualizer.set_state("thinking")

    def _on_recorded(self, audio):
        """The recorder finished (button released, or the maximum length was reached)."""
        self._recording = False
        self._transcribing = True
        seconds = len(audio) / SAMPLE_RATE
        if seconds < MIN_RECORD_SECONDS:
            self._voice_done("Too short. Hold the button while you speak.")
            return
        rms = float(np.sqrt(np.mean(audio * audio)))
        if rms < SILENCE_RMS_THRESHOLD:
            self._voice_done("I didn't hear anything. Check your microphone.")
            return

        self.input_bar.set_mic_state("processing")
        self.input_bar.set_busy(True)
        self._set_state("thinking", "Transcribing...")
        worker = TranscribeWorker(self.stt, audio, parent=self)
        worker.transcribed.connect(self._on_transcribed)
        worker.failed.connect(self._on_voice_failed)
        self._start_thread(worker)

    def _on_transcribed(self, text: str):
        self._transcribing = False
        self.input_bar.set_mic_state("idle")
        if not text:
            self._voice_done("I couldn't make out any words. Please try again.")
            return
        self._submit_to_ai(text, from_voice=True)

    def _on_recorder_failed(self, kind: str, message: str):
        self._voice_done(None, error=message)

    def _on_voice_failed(self, kind: str, message: str):
        self._voice_done(None, error=message)

    def _voice_done(self, notice: str | None, error: str | None = None):
        """Leave the voice pipeline without sending anything to the AI."""
        self._recording = False
        self._transcribing = False
        self.input_bar.set_mic_state("idle")
        self.input_bar.set_busy(False)
        if error:
            self.chat.add_message("error", error)
        if notice:
            self._flash_status(notice)
        else:
            self._set_state(self._rest_state())

    # ------------------------------------------------------------------ speaking
    def _speech_end(self):
        self.speech.end_of_reply()
        self._speech_ends_pending += 1

    def _speech_stop(self):
        """Stop talking immediately (does nothing if no speech is pending)."""
        if self._speech_ends_pending > 0:
            self.speech.stop_speaking()
            self._speech_ends_pending += 1

    def _on_speaking_started(self):
        if self._recording or self._transcribing:
            return
        self._set_state("speaking")

    def _on_speaking_finished(self):
        self._speech_ends_pending = max(0, self._speech_ends_pending - 1)
        if self._is_idle() and self._speech_ends_pending == 0:
            self._set_state("idle")

    def _on_speech_failed(self, kind: str, message: str):
        self.chat.add_message("error", message)

    def _on_voice_replies_toggled(self, on: bool):
        self._voice_replies_on = on
        if not on:
            self._speech_stop()

    def _on_escape(self):
        """Esc: deny a pending permission prompt, or close settings, or stop the speech."""
        if self._pending_card is not None:
            self._pending_card.deny()
        elif self._settings_open:
            self._close_settings()
        else:
            self._speech_stop()

    # ------------------------------------------------------------------ sidebar
    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    # ------------------------------------------------------------------ settings
    def _settings_rect(self, open_: bool) -> QRect:
        height = self.central.height() - 2 * SETTINGS_MARGIN
        x = (self.central.width() - SETTINGS_WIDTH - SETTINGS_MARGIN) if open_ \
            else self.central.width() + 20
        return QRect(x, SETTINGS_MARGIN, SETTINGS_WIDTH, height)

    def _animate_settings(self, open_: bool):
        self._settings_open = open_
        self._settings_anim.stop()
        if open_:
            self.settings.setGeometry(self._settings_rect(False))
            self.settings.show()
            self.settings.raise_()
        self._settings_anim.setStartValue(self.settings.geometry())
        self._settings_anim.setEndValue(self._settings_rect(open_))
        self._settings_anim.start()

    def _on_settings_anim_finished(self):
        if not self._settings_open:
            self.settings.hide()

    def _toggle_settings(self):
        self._animate_settings(not self._settings_open)

    def _close_settings(self):
        if self._settings_open:
            self._animate_settings(False)

    # ------------------------------------------------------------------ responsiveness
    def _on_central_resized(self):
        narrow = self.central.width() < NARROW_BREAKPOINT
        if narrow != self._narrow:
            self._narrow = narrow
            self.sidebar.setVisible(not narrow)
        if self._settings_open and self._settings_anim.state() != QPropertyAnimation.Running:
            self.settings.setGeometry(self._settings_rect(True))

    # ------------------------------------------------------------------ Windows polish
    def showEvent(self, event):
        super().showEvent(event)
        if not self._title_bar_done:
            self._title_bar_done = True
            self._apply_dark_title_bar()

    def _apply_dark_title_bar(self):
        """Ask Windows 10/11 for a dark title bar. Purely cosmetic; ignored if unsupported."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(int(self.winId())), 20, ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass