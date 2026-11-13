"""
AIVisualizer - the animated orb at the heart of the interface.

It draws a glowing core, a ring of radial bars that move like an audio
spectrum, and a slowly rotating dotted ring. Four states change the speed
and intensity: idle, listening, thinking, speaking.

Right now the motion is simulated. In later phases the same widget can be
fed real microphone levels.
"""
import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QFont, QPainter, QPen, QRadialGradient, QColor
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.ui.theme import FONT_FAMILY, Colors, mix, rgba


class AIVisualizer(QWidget):
    # state -> (animation speed, bar intensity, caption)
    STATES = {
        "idle": (0.7, 0.12, "STANDBY"),
        "listening": (1.8, 0.55, "LISTENING"),
        "thinking": (3.2, 0.35, "THINKING"),
        "speaking": (2.4, 0.85, "SPEAKING"),
    }
    BAR_COUNT = 72
    FRAME_MS = 16  # ~60 frames per second. Use 33 for ~30 fps if your laptop struggles.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._state = "idle"
        self._speed = self.STATES["idle"][0]  # Current (eased) values
        self._amp = self.STATES["idle"][1]
        self._phase = 0.0                      # Drives the wave motion
        self._spin = 0.0                       # Rotation of the dotted ring (degrees)
        self._animated = True

        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ----- public API -----
    def set_state(self, state: str):
        """Switch between idle / listening / thinking / speaking."""
        if state in self.STATES:
            self._state = state
            self.update()

    def set_animated(self, enabled: bool):
        """Turn the animation on or off (used by the Settings panel)."""
        self._animated = enabled
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    # ----- animation step -----
    def _tick(self):
        """Called every frame: ease toward the target state's values and advance time."""
        target_speed, target_amp, _ = self.STATES[self._state]
        self._speed += (target_speed - self._speed) * 0.06  # Smooth transition
        self._amp += (target_amp - self._amp) * 0.06
        self._phase += 0.016 * self._speed * 2.0
        self._spin = (self._spin + self._speed * 0.8) % 360
        self.update()  # Ask Qt to repaint

    # ----- drawing -----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        caption_h = 26
        area_h = h - caption_h
        cx, cy = w / 2, area_h / 2 + 4
        size = min(w, area_h)
        r = size * 0.22  # Core radius

        # 1) Soft background glow that breathes
        glow_r = r * (2.3 + 0.4 * self._amp * math.sin(self._phase * 2))
        glow = QRadialGradient(QPointF(cx, cy), glow_r)
        glow.setColorAt(0.0, rgba(Colors.ACCENT, 0.35))
        glow.setColorAt(0.5, rgba(Colors.ACCENT, 0.10))
        glow.setColorAt(1.0, rgba(Colors.ACCENT, 0.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        painter.save()
        painter.translate(cx, cy)

        # 2) Radial bars around the core
        inner = r * 1.25
        max_len = max(6.0, size * 0.5 - inner - 2)
        pen = QPen()
        pen.setWidthF(max(2.0, size * 0.012))
        pen.setCapStyle(Qt.RoundCap)
        for i in range(self.BAR_COUNT):
            angle = 2 * math.pi * i / self.BAR_COUNT
            wave1 = 0.5 + 0.5 * math.sin(self._phase * 2.0 + i * 0.55)
            wave2 = 0.5 + 0.5 * math.sin(self._phase * 1.3 - i * 0.23 + 1.7)
            length = 3 + max_len * self._amp * wave1 * (0.35 + 0.65 * wave2)
            color = mix(Colors.ACCENT, Colors.ACCENT_CYAN,
                        0.5 + 0.5 * math.sin(angle * 2 + self._phase))
            pen.setColor(rgba(color, 0.35 + 0.6 * wave1))
            painter.setPen(pen)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            painter.drawLine(QPointF(inner * cos_a, inner * sin_a),
                             QPointF((inner + length) * cos_a, (inner + length) * sin_a))

        # 3) Rotating dotted ring
        painter.save()
        painter.rotate(self._spin)
        ring_pen = QPen(rgba(Colors.ACCENT_LIGHT, 0.55), 1.4)
        ring_pen.setDashPattern([1.0, 7.0])
        ring_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r * 1.12, r * 1.12)
        painter.restore()

        # 4) Glassy core orb with an off-centre highlight
        core_r = r * (0.92 + 0.06 * math.sin(self._phase * 2.0) * (0.4 + self._amp))
        orb = QRadialGradient(QPointF(0, 0), core_r, QPointF(-core_r * 0.35, -core_r * 0.35))
        orb.setColorAt(0.0, QColor("#bfdbfe"))
        orb.setColorAt(0.45, QColor(Colors.ACCENT))
        orb.setColorAt(1.0, QColor(Colors.ACCENT_DEEP))
        painter.setBrush(orb)
        painter.setPen(QPen(rgba("#ffffff", 0.35), 1.2))
        painter.drawEllipse(QPointF(0, 0), core_r, core_r)
        painter.restore()

        # 5) State caption under the orb
        font = QFont(FONT_FAMILY, 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 3.0)
        painter.setFont(font)
        painter.setPen(rgba(Colors.TEXT_DIM, 0.9))
        painter.drawText(QRectF(0, h - caption_h, w, caption_h), Qt.AlignCenter,
                         self.STATES[self._state][2])