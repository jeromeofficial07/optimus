"""
MainWindow - assembles every component and wires them together.

Phase 2 has NO AI. When you send a message, a placeholder reply is produced
after a short delay so you can test the bubbles, typing dots and visualizer
states. The marked placeholder section is what a later phase replaces.
"""
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout

from app.config import APP_NAME
from app.ui.chat_widgets import ChatView
from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.icon_button import IconButton
from app.ui.input_bar import InputBar
from app.ui.settings_panel import SettingsPanel
from app.ui.sidebar import Sidebar
from app.ui.status_indicator import StatusIndicator
from app.ui.visualizer import AIVisualizer

SETTINGS_WIDTH = 330
SETTINGS_MARGIN = 18
NARROW_BREAKPOINT = 1000  # Below this width the sidebar auto-hides


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}")
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        self._narrow = False
        self._settings_open = False
        self._busy = False
        self._title_bar_done = False

        self.central = BackgroundWidget()
        self.setCentralWidget(self.central)

        self._build_ui()
        self._connect_signals()
        self._show_welcome()

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
        root.addLayout(column, 1)  # stretch=1 -> takes all remaining width

        # Top bar: menu button, status, settings button
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

        # Visualizer panel (stretch 2) and chat panel (stretch 5): they share the
        # height in a 2:5 ratio, so both resize proportionally with the window.
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

        # Settings overlay: a child of the backdrop, NOT in a layout, so we can
        # position and animate it freely on top of everything else.
        self.settings = SettingsPanel(self.central)
        self.settings.hide()

        # One reusable slide animation for the settings panel
        self._settings_anim = QPropertyAnimation(self.settings, b"geometry", self)
        self._settings_anim.setDuration(340)
        self._settings_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._settings_anim.finished.connect(self._on_settings_anim_finished)

    def _connect_signals(self):
        """Connect widget signals to the methods that handle them."""
        self.sidebar.new_chat_requested.connect(self._new_chat)
        self.sidebar.conversation_selected.connect(self._open_conversation)

        self.input_bar.message_submitted.connect(self._on_user_message)
        self.input_bar.mic_toggled.connect(self._on_mic_toggled)

        self.menu_button.clicked.connect(self._toggle_sidebar)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.settings.closed.connect(self._close_settings)

        self.settings.animations_toggled.connect(self.visualizer.set_animated)
        self.settings.timestamps_toggled.connect(self.chat.set_timestamps_visible)
        self.settings.font_size_changed.connect(self.chat.set_font_size)

        self.central.resized.connect(self._on_central_resized)

        escape = QShortcut(QKeySequence("Esc"), self)
        escape.activated.connect(self._close_settings)

    # ------------------------------------------------------------------ state
    def _rest_state(self) -> str:
        """The state to return to when nothing is happening."""
        return "listening" if self.input_bar.mic_button.isChecked() else "idle"

    def _set_state(self, state: str):
        """Update the visualizer AND the status indicator together."""
        self.visualizer.set_state(state)
        status_map = {
            "idle": ("ready", "Systems ready"),
            "listening": ("listening", "Listening"),
            "thinking": ("busy", "Processing"),
            "speaking": ("busy", "Responding"),
        }
        key, text = status_map[state]
        self.status.set_status(key, text)

    # ------------------------------------------------------------------ chat flow
    def _show_welcome(self):
        self.chat.add_message(
            "assistant",
            "Hello, I'm OPTIMUS. My interface is online. "
            "AI, voice and tools will be connected in later phases.",
        )

    def _new_chat(self):
        self.chat.clear()
        self.sidebar.add_conversation("New conversation")
        self._show_welcome()

    def _open_conversation(self, title: str):
        self.chat.clear()
        self.chat.add_message(
            "assistant",
            f"Placeholder: the conversation '{title}' will be loaded from the "
            "database once persistent memory is added.",
        )

    def _on_user_message(self, text: str):
        """User sent a message: show it, then simulate a short 'thinking' period."""
        if self._busy:
            return
        self._busy = True
        self.chat.add_message("user", text)
        self.input_bar.set_busy(True)
        self._set_state("thinking")
        self.chat.show_typing()

        # ===== PLACEHOLDER (replaced when the AI is connected) =====
        QTimer.singleShot(1100, lambda: self._placeholder_reply(text))

    def _placeholder_reply(self, text: str):
        self.chat.hide_typing()
        self._set_state("speaking")
        self.chat.add_message(
            "assistant",
            f"[Interface test] You said: \"{text}\"\n\n"
            "This is a placeholder reply. The AI is not connected yet.",
        )
        QTimer.singleShot(2000, self._finish_reply)

    def _finish_reply(self):
        self._busy = False
        self.input_bar.set_busy(False)
        self._set_state(self._rest_state())
        # ===== END PLACEHOLDER =====

    def _on_mic_toggled(self, on: bool):
        self.input_bar.set_listening_hint(on)
        if not self._busy:
            self._set_state("listening" if on else "idle")

    # ------------------------------------------------------------------ sidebar
    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    # ------------------------------------------------------------------ settings
    def _settings_rect(self, open_: bool) -> QRect:
        """Where the settings panel should be: on screen (open) or just off the right edge."""
        height = self.central.height() - 2 * SETTINGS_MARGIN
        x = (self.central.width() - SETTINGS_WIDTH - SETTINGS_MARGIN) if open_ \
            else self.central.width() + 20
        return QRect(x, SETTINGS_MARGIN, SETTINGS_WIDTH, height)

    def _animate_settings(self, open_: bool):
        """Slide the panel in or out."""
        self._settings_open = open_
        self._settings_anim.stop()
        if open_:
            self.settings.setGeometry(self._settings_rect(False))  # Start off-screen
            self.settings.show()
            self.settings.raise_()  # Draw above every other widget
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
        """React to window size changes."""
        narrow = self.central.width() < NARROW_BREAKPOINT
        if narrow != self._narrow:  # Only act when crossing the breakpoint
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