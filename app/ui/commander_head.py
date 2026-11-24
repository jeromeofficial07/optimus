"""
CommanderVisualizer - the animated robot head (original artwork, drawn in code).
Same states, timer and speed behaviour as the orb; only the drawing is different.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from app.ui.theme import FONT_FAMILY, Colors, mix, rgba
from app.ui.visualizer import AIVisualizer

EYE_COLORS = {"idle": "#3b8dff", "listening": "#5fe8ff", "thinking": "#ffb454", "speaking": "#9be9ff"}


def _pen(color, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)           # Keeps the line width the same however large the head is drawn
    return pen


def _poly(*points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def _mirror(poly: QPolygonF) -> QPolygonF:
    pts = [poly.at(i) for i in range(poly.count())]
    return QPolygonF([QPointF(-pt.x(), pt.y()) for pt in reversed(pts)])


class CommanderVisualizer(AIVisualizer):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._boot = 0.0                 # 0 -> 1 over the first seconds: the head powers up
        self._helmet = _poly((-0.60, -0.52), (-0.36, -0.86), (0.36, -0.86), (0.60, -0.52), (0.68, 0.04),
                             (0.52, 0.60), (0.24, 0.90), (-0.24, 0.90), (-0.52, 0.60), (-0.68, 0.04))
        self._crest = _poly((-0.15, -0.86), (0.15, -0.86), (0.09, -0.38), (-0.09, -0.38))
        self._fin_l = _poly((-0.68, -0.18), (-0.92, -0.40), (-0.96, 0.16), (-0.68, 0.28))
        self._fin_r = _mirror(self._fin_l)
        self._visor = _poly((-0.54, -0.26), (0.54, -0.26), (0.44, 0.04), (-0.44, 0.04))
        self._eye_l = _poly((-0.48, -0.21), (-0.09, -0.21), (-0.15, -0.04), (-0.42, -0.04))
        self._eye_r = _mirror(self._eye_l)
        self._vent = _poly((-0.045, 0.06), (0.045, 0.06), (0.07, 0.34), (-0.07, 0.34))
        self._cheek_l = _poly((-0.54, 0.12), (-0.22, 0.32), (-0.22, 0.76), (-0.42, 0.62))
        self._cheek_r = _mirror(self._cheek_l)
        self._mouth = _poly((-0.24, 0.44), (0.24, 0.44), (0.18, 0.74), (-0.18, 0.74))
        self._mouth_gap = _poly((-0.26, 0.42), (0.26, 0.42), (0.20, 0.80), (-0.20, 0.80))

    def _tick(self):
        super()._tick()
        if self._boot < 1.0:
            self._boot = min(1.0, self._boot + 0.012)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        caption_h = 26
        area_h = h - caption_h
        cx, cy = w / 2, area_h / 2
        s = max(20.0, min(w * 0.30, area_h * 0.5) * 0.92)           # Pixels per drawing unit
        phase, amp, state, boot = self._phase, self._amp, self._state, self._boot
        eye = QColor(EYE_COLORS[state])

        if state == "idle":
            glow = 0.55 + 0.12 * math.sin(phase * 1.2)
        elif state == "listening":
            glow = 0.80 + 0.20 * math.sin(phase * 4.0)
        elif state == "thinking":
            glow = 0.85
        else:
            glow = 0.70 + 0.30 * abs(math.sin(phase * 3.0))
        glow *= boot
        if state == "speaking":
            jaw = abs(math.sin(phase * 3.1)) * (0.45 + 0.55 * abs(math.sin(phase * 1.7)))
        elif state == "listening":
            jaw = 0.12 * abs(math.sin(phase * 2.0))
        else:
            jaw = 0.0

        # Soft red aura behind the head
        aura = QRadialGradient(QPointF(cx, cy), s * 2.0)
        aura.setColorAt(0.0, rgba(Colors.ACCENT, 0.20 * boot))
        aura.setColorAt(1.0, rgba(Colors.ACCENT, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(aura))
        p.drawEllipse(QPointF(cx, cy), s * 2.0, s * 2.0)

        p.save()
        p.translate(cx, cy)

        # HUD rings: blue dashes turn one way, red arcs the other
        outer, inner = s * 1.30, s * 1.15
        p.setPen(QPen(rgba(Colors.ACCENT_CYAN, 0.55 * boot), 3.0))
        for i in range(18):
            p.drawArc(QRectF(-outer, -outer, 2 * outer, 2 * outer), int((i * 20 + self._spin) * 16), 11 * 16)
        p.setPen(QPen(rgba(Colors.ACCENT, 0.75 * boot), 1.6))
        for i in range(6):
            p.drawArc(QRectF(-inner, -inner, 2 * inner, 2 * inner), int((i * 60 - self._spin * 1.6) * 16), 34 * 16)

        # Voice bars on both sides, shaded from red to blue
        x0, gap = s * 1.60, max(7.0, s * 0.12)
        count = max(0, min(14, int((w / 2 - 16 - x0) / gap)))
        bar = QPen()
        bar.setWidthF(max(3.0, s * 0.05))
        bar.setCapStyle(Qt.RoundCap)
        for side in (-1, 1):
            for i in range(count):
                wave = 0.5 + 0.5 * math.sin(phase * 2.2 + i * 0.7 + (0.0 if side > 0 else 1.3))
                height_px = s * (0.14 + 0.55 * amp * wave * (1.0 - i / (count * 1.25)))
                bar.setColor(rgba(mix(Colors.ACCENT, Colors.ACCENT_CYAN, i / max(1, count - 1)),
                                  (0.35 + 0.55 * wave) * boot))
                p.setPen(bar)
                x = side * (x0 + i * gap)
                p.drawLine(QPointF(x, -height_px), QPointF(x, height_px))

        # The head, in drawing units (about -1 to +1)
        p.scale(s, s)
        steel = QLinearGradient(0, -0.9, 0, 0.9)
        steel.setColorAt(0.0, rgba("#3b4f85", boot))
        steel.setColorAt(0.45, rgba("#26355f", boot))
        steel.setColorAt(1.0, rgba("#101a33", boot))
        red = QLinearGradient(0, -0.9, 0, 0.3)
        red.setColorAt(0.0, rgba(Colors.ACCENT_LIGHT, boot))
        red.setColorAt(1.0, rgba(Colors.ACCENT_DEEP, boot))
        edge = _pen(rgba("#9fb4e6", 0.85 * boot), 1.6)
        red_edge = _pen(rgba(Colors.ACCENT_LIGHT, 0.9 * boot), 1.4)

        p.setBrush(QBrush(red))                                            # Side fins
        p.setPen(red_edge)
        p.drawPolygon(self._fin_l)
        p.drawPolygon(self._fin_r)
        p.setBrush(QBrush(steel))                                          # Helmet
        p.setPen(edge)
        p.drawPolygon(self._helmet)
        p.setBrush(QBrush(red))                                            # Crest
        p.setPen(red_edge)
        p.drawPolygon(self._crest)
        p.setBrush(rgba("#05070f", boot))                                  # Visor
        p.setPen(edge)
        p.drawPolygon(self._visor)

        for ex in (-0.27, 0.27):                                           # Eye glow
            halo = QRadialGradient(QPointF(ex, -0.125), 0.42)
            halo.setColorAt(0.0, rgba(eye, 0.55 * glow))
            halo.setColorAt(1.0, rgba(eye, 0.0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(ex, -0.125), 0.42, 0.42)
        p.setBrush(rgba(eye, min(1.0, 0.25 + 0.75 * glow)))                # Eyes
        p.setPen(_pen(rgba("#ffffff", 0.6 * glow), 1.0))
        p.drawPolygon(self._eye_l)
        p.drawPolygon(self._eye_r)

        if state == "thinking":                                            # Scanner beam across the visor
            p.save()
            clip = QPainterPath()
            clip.addPolygon(self._visor)
            p.setClipPath(clip)
            x = math.sin(phase * 1.6) * 0.46
            beam = QLinearGradient(x - 0.14, 0, x + 0.14, 0)
            beam.setColorAt(0.0, rgba("#ffffff", 0.0))
            beam.setColorAt(0.5, rgba("#fff1c9", 0.95 * boot))
            beam.setColorAt(1.0, rgba("#ffffff", 0.0))
            p.setPen(Qt.NoPen)
            p.fillRect(QRectF(-0.6, -0.3, 1.2, 0.4), QBrush(beam))
            p.restore()

        p.setBrush(rgba("#0a1124", boot))                                  # Vent and cheek plates
        p.setPen(_pen(rgba("#5d74ad", 0.8 * boot), 1.2))
        p.drawPolygon(self._vent)
        p.setBrush(QBrush(steel))
        p.drawPolygon(self._cheek_l)
        p.drawPolygon(self._cheek_r)

        p.setBrush(rgba("#04060c", boot))                                  # Dark gap, revealed as the jaw drops
        p.setPen(Qt.NoPen)
        p.drawPolygon(self._mouth_gap)
        p.save()
        p.translate(0, jaw * 0.07)                                         # The jaw plate moves with speech
        plate = QLinearGradient(0, 0.44, 0, 0.74)
        plate.setColorAt(0.0, rgba("#5a6f9f", boot))
        plate.setColorAt(1.0, rgba("#23335a", boot))
        p.setBrush(QBrush(plate))
        p.setPen(edge)
        p.drawPolygon(self._mouth)
        p.setPen(_pen(rgba("#0a1124", 0.9 * boot), 1.4))
        for k in range(4):
            y = 0.50 + k * 0.065
            p.drawLine(QPointF(-0.14, y), QPointF(0.14, y))
        p.restore()

        p.setPen(Qt.NoPen)                                                 # Rivets
        p.setBrush(rgba("#c8d6f5", 0.7 * boot))
        for rx, ry in ((-0.50, -0.45), (0.50, -0.45), (-0.60, 0.0), (0.60, 0.0), (0.0, 0.84)):
            p.drawEllipse(QPointF(rx, ry), 0.018, 0.018)
        p.restore()

        font = QFont(FONT_FAMILY, 9)                                       # State caption
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 3.0)
        p.setFont(font)
        p.setPen(rgba(Colors.TEXT_DIM, 0.95))
        p.drawText(QRectF(0, h - caption_h, w, caption_h), Qt.AlignCenter, f"//  {self.STATES[state][2]}  //")


# --- end of file ---