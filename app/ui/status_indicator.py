"""
StatusIndicator - a small pulsing dot plus a text label showing system state.
"""
from PySide6.QtCore import QPointF, QVariantAnimation, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui.theme import Colors, rgba


class _PulseDot(QWidget):
    """The dot itself: a solid centre with a halo that expands and fades."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._color = Colors.SUCCESS
        self._pulse = 0.0  # 0 to 1, driven by the animation in StatusIndicator

    def set_color(self, color: str):
        self._color = color
        self.update()

    def set_pulse(self, value: float):
        self._pulse = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.setPen(Qt.NoPen)

        halo_radius = 4 + 7 * self._pulse           # Grows outward...
        painter.setBrush(rgba(self._color, 0.45 * (1 - self._pulse)))  # ...while fading
        painter.drawEllipse(center, halo_radius, halo_radius)

        painter.setBrush(rgba(self._color, 1.0))
        painter.drawEllipse(center, 4, 4)


class StatusIndicator(QWidget):
    # key -> (dot colour, default text)
    STATES = {
        "ready": (Colors.SUCCESS, "Systems ready"),
        "busy": (Colors.WARNING, "Processing"),
        "listening": (Colors.ACCENT_LIGHT, "Listening"),
        "offline": (Colors.DANGER, "Offline"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot = _PulseDot()
        self._label = QLabel("Systems ready")
        self._label.setObjectName("StatusText")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

        # Endless 0 -> 1 animation that drives the pulsing halo
        self._pulse = QVariantAnimation(self)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.setDuration(1600)
        self._pulse.setLoopCount(-1)  # -1 = repeat forever
        self._pulse.valueChanged.connect(self._dot.set_pulse)
        self._pulse.start()

        self.set_status("ready")

    def set_status(self, key: str, text: str | None = None):
        """Change colour and text. key is one of STATES; text overrides the default."""
        color, default_text = self.STATES[key]
        self._dot.set_color(color)
        self._label.setText(text or default_text)
        self._pulse.setDuration(700 if key == "busy" else 1600)  # Pulse faster when busy