"""
InputBar - text field, level meter, push-to-talk microphone button and send button.

It knows nothing about AI or audio. It only emits signals:
    message_submitted(text) - Enter or the send button
    mic_pressed()           - microphone button pushed down (start recording)
    mic_released()          - microphone button let go (stop recording)
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit

from app.ui.glass_panel import GlassPanel
from app.ui.icon_button import IconButton
from app.ui.mic_meter import MicMeter

DEFAULT_PLACEHOLDER = "Message OPTIMUS...   (or hold the mic button / Ctrl+Space to talk)"


class InputBar(GlassPanel):
    message_submitted = Signal(str)
    mic_pressed = Signal()
    mic_released = Signal()

    def __init__(self, parent=None):
        super().__init__(radius=30, tint=0.6, parent=parent)
        self.setFixedHeight(68)
        self._mic_active = False  # True only while the microphone is really recording

        self.input = QLineEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText(DEFAULT_PLACEHOLDER)

        self.mic_meter = MicMeter()
        self.mic_meter.hide()

        self.mic_button = IconButton("mic", size=44, tooltip="Hold to talk (or hold Ctrl+Space)",
                                     checkable=True)
        self.send_button = IconButton("send", size=44, tooltip="Send (Enter)", filled=True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.input, 1)
        layout.addWidget(self.mic_meter)
        layout.addWidget(self.mic_button)
        layout.addWidget(self.send_button)

        self.input.returnPressed.connect(self._submit)
        self.send_button.clicked.connect(self._submit)
        self.mic_button.pressed.connect(self.mic_pressed)     # Forward the signals
        self.mic_button.released.connect(self._on_mic_released)

    def _submit(self):
        """Read the text, ignore empty input, clear the field and announce the message."""
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def _on_mic_released(self):
        self.mic_released.emit()
        # A checkable button flips its state on every click; force it back to the truth
        self.mic_button.setChecked(self._mic_active)

    def set_mic_state(self, state: str):
        """state: 'idle', 'recording' or 'processing'. Updates the button, meter and hint text."""
        recording = state == "recording"
        self._mic_active = recording
        self.mic_button.setChecked(recording)   # Glows blue while recording
        self.mic_meter.setVisible(recording)
        self.input.setPlaceholderText({
            "recording": "Listening...  release to send",
            "processing": "Processing your voice...",
        }.get(state, DEFAULT_PLACEHOLDER))

    def set_level(self, level: float):
        """Live microphone loudness (0..1) for the meter."""
        self.mic_meter.set_level(level)

    def set_busy(self, busy: bool):
        """Lock the input while something is being processed."""
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.mic_button.setEnabled(not busy)
        if not busy:
            self.input.setFocus()