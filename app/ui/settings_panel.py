"""
SettingsPanel - a glass panel that slides in from the right.
MainWindow positions and animates it; this file only builds its contents.
"""
from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF, Qt,
                            Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QSlider,
                               QVBoxLayout, QWidget)

from app.ui.glass_panel import GlassPanel
from app.ui.icon_button import IconButton
from app.ui.theme import Colors, mix


class ToggleSwitch(QCheckBox):
    """An iOS-style on/off switch with an animated knob."""

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._offset = 1.0 if checked else 0.0  # Knob position: 0 = left, 1 = right

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float):
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def hitButton(self, pos):
        """Make the whole switch clickable, not just a tiny indicator."""
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = track.height() / 2

        # Track colour blends from grey to blue as the knob moves
        painter.setPen(Qt.NoPen)
        painter.setBrush(mix(QColor(255, 255, 255, 45), Colors.ACCENT, self._offset))
        painter.drawRoundedRect(track, radius, radius)

        # Knob
        d = track.height() - 6
        x = track.left() + 3 + self._offset * (track.width() - d - 6)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x, track.top() + 3, d, d))


class SettingRow(QWidget):
    """Title + description on the left, toggle switch on the right."""

    def __init__(self, title: str, description: str, checked: bool, parent=None):
        super().__init__(parent)
        title_label = QLabel(title)
        title_label.setObjectName("SettingTitle")
        desc_label = QLabel(description)
        desc_label.setObjectName("SettingDesc")
        desc_label.setWordWrap(True)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        text_column.addWidget(title_label)
        text_column.addWidget(desc_label)

        self.switch = ToggleSwitch(checked)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addLayout(text_column, 1)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)


class SettingsPanel(GlassPanel):
    closed = Signal()
    animations_toggled = Signal(bool)
    timestamps_toggled = Signal(bool)
    voice_replies_toggled = Signal(bool)
    font_size_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(radius=26, tint=0.93, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        # Header: title + close button
        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("PanelTitle")
        close_button = IconButton("close", size=36, tooltip="Close")
        close_button.clicked.connect(self.closed)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_button)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # Toggles
        animations = SettingRow("Animated visualizer", "Smooth real-time animation of the AI orb.", True)
        timestamps = SettingRow("Show timestamps", "Display the time under each message.", True)
        voice = SettingRow("Voice replies", "Speak every answer aloud. Spoken questions are always answered by voice.", False)
        animations.switch.toggled.connect(self.animations_toggled)
        timestamps.switch.toggled.connect(self.timestamps_toggled)
        voice.switch.toggled.connect(self.voice_replies_toggled)
        for row in (animations, timestamps, voice):
            layout.addWidget(row)

        # Text size slider
        size_title = QLabel("Chat text size")
        size_title.setObjectName("SettingTitle")
        self._size_value = QLabel("15 px")
        self._size_value.setObjectName("SettingDesc")
        size_header = QHBoxLayout()
        size_header.addWidget(size_title)
        size_header.addStretch(1)
        size_header.addWidget(self._size_value)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(12, 20)
        slider.setValue(15)
        slider.valueChanged.connect(self._on_size_changed)

        layout.addLayout(size_header)
        layout.addWidget(slider)

        layout.addStretch(1)
        note = QLabel("Settings last for this session only for now.")
        note.setObjectName("Footer")
        layout.addWidget(note)

    def _on_size_changed(self, value: int):
        self._size_value.setText(f"{value} px")
        self.font_size_changed.emit(value)