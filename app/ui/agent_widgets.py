"""
Widgets that show agent activity inside the chat:

ActionChip       - a small pill saying what OPTIMUS just did (or could not do)
ConfirmationCard - an Allow / Deny prompt for sensitive or destructive actions
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.config import CONFIRMATION_TIMEOUT
from app.ui.theme import Colors, qss_rgba


class ActionChip(QFrame):
    def __init__(self, ok: bool, text: str, parent=None):
        super().__init__(parent)
        color = Colors.SUCCESS if ok else Colors.DANGER
        self.setObjectName("ActionChip")
        self.setMaximumWidth(560)
        self.setStyleSheet(
            f"QFrame#ActionChip {{ background: {qss_rgba(color, 0.12)};"
            f" border: 1px solid {qss_rgba(color, 0.45)}; border-radius: 14px; }}"
        )
        label = QLabel(("✓  " if ok else "✗  ") + text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {color}; font-size: 13px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.addWidget(label)


class ConfirmationCard(QFrame):
    """Asks the user to allow or deny an action. Auto-denies when the timer runs out."""
    decided = Signal(bool)  # True = allowed

    def __init__(self, title: str, description: str, risk: str, parent=None):
        super().__init__(parent)
        accent = {"destructive": Colors.DANGER, "sensitive": Colors.WARNING}.get(risk, Colors.ACCENT_LIGHT)
        self.setObjectName("ConfirmCard")
        self.setMaximumWidth(560)
        self.setStyleSheet(f"""
            QFrame#ConfirmCard {{ background: rgba(255,255,255,18);
                border: 1px solid {qss_rgba(accent, 0.7)}; border-radius: 16px; }}
            QPushButton#DenyButton {{ color: {Colors.TEXT}; font-size: 13px; font-weight: 600;
                background: rgba(255,255,255,20); border: 1px solid rgba(255,255,255,50);
                border-radius: 12px; padding: 10px 18px; }}
            QPushButton#DenyButton:hover {{ background: rgba(255,255,255,36); }}
        """)
        self._decided = False
        self._remaining = CONFIRMATION_TIMEOUT

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {accent}; font-size: 14px; font-weight: 600;")
        text_label = QLabel(description)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-size: 14px;")
        self._countdown = QLabel(f"Auto-deny in {self._remaining} s")
        self._countdown.setObjectName("SettingDesc")

        self._allow = QPushButton("Allow")
        self._allow.setObjectName("PrimaryButton")
        self._deny = QPushButton("Deny")
        self._deny.setObjectName("DenyButton")
        for button in (self._allow, self._deny):
            button.setCursor(Qt.PointingHandCursor)
        self._allow.clicked.connect(lambda: self._decide(True))
        self._deny.clicked.connect(lambda: self._decide(False))

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self._allow)
        buttons.addWidget(self._deny)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        layout.addLayout(buttons)
        layout.addWidget(self._countdown)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._remaining -= 1
        self._countdown.setText(f"Auto-deny in {self._remaining} s")
        if self._remaining <= 0:
            self._decide(False)

    def deny(self):
        """Used by the Esc key."""
        self._decide(False)

    def _decide(self, allowed: bool):
        if self._decided:
            return
        self._decided = True
        self._timer.stop()
        self._allow.setEnabled(False)
        self._deny.setEnabled(False)
        self._countdown.setText("✓ Allowed" if allowed else "✗ Denied")
        self.decided.emit(allowed)