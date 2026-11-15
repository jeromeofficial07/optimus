"""
MicMeter - a small set of bouncing bars that reacts to how loud you are speaking.
It only appears while the microphone is recording.
"""
import math

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.ui.theme import Colors, rgba


class MicMeter(QWidget):
    BARS = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 30)
        self._level = 0.0    # Latest value from the microphone (0..1)
        self._smooth = 0.0   # Eased value used for drawing, so bars move smoothly
        self._t = 0.0        # Time, gives each bar its own wobble

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))

    def showEvent(self, event):    # Only animate while visible
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        self._level = 0.0
        self._smooth = 0.0
        super().hideEvent(event)

    def _tick(self):
        self._smooth += (self._level - self._smooth) * 0.4
        self._t += 0.35
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        gap = w / self.BARS

        pen = QPen()
        pen.setWidthF(3.2)
        pen.setCapStyle(Qt.RoundCap)
        for i in range(self.BARS):
            wobble = 0.55 + 0.45 * math.sin(self._t + i * 0.9)
            bar_height = 4 + (h - 8) * self._smooth * wobble
            x = gap * (i + 0.5)
            pen.setColor(rgba(Colors.ACCENT_CYAN, 0.5 + 0.5 * self._smooth))
            painter.setPen(pen)
            painter.drawLine(QPointF(x, h / 2 - bar_height / 2), QPointF(x, h / 2 + bar_height / 2))