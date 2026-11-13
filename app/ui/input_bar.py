"""
InputBar - the bottom bar with the text field, microphone button and send button.

It does not know anything about AI. It only emits signals:
    message_submitted(text)  - user pressed Enter or the send button
    mic_toggled(bool)        - microphone button switched on/off
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit

from app.ui.glass_panel import GlassPanel
from app.ui.icon_button import IconButton


class InputBar(GlassPanel):
    message_submitted = Signal(str)
    mic_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(radius=30, tint=0.6, parent=parent)
        self.setFixedHeight(68)

        self.input = QLineEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Message OPTIMUS...")

        self.mic_button = IconButton("mic", size=44, tooltip="Voice input", checkable=True)
        self.send_button = IconButton("send", size=44, tooltip="Send (Enter)", filled=True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.input, 1)
        layout.addWidget(self.mic_button)
        layout.addWidget(self.send_button)

        self.input.returnPressed.connect(self._submit)      # Enter key
        self.send_button.clicked.connect(self._submit)      # Send button
        self.mic_button.toggled.connect(self.mic_toggled)   # Forward the signal

    def _submit(self):
        """Read the text, ignore empty input, clear the field and announce the message."""
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def set_busy(self, busy: bool):
        """Disable sending while a reply is being produced."""
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def set_listening_hint(self, listening: bool):
        """Change the placeholder text while the mic button is on."""
        self.input.setPlaceholderText(
            "Listening... (voice input arrives in a later phase)" if listening
            else "Message OPTIMUS..."
        )