"""
BlueprintVisualizer - an animated technical drawing of the assistant (original design).

It subclasses the orb, so states, timer and animation speed are unchanged; only the drawing differs.
  * the schematic draws itself on after the intro (boot goes -1 -> 0 -> 1)
  * the eyes and details follow the mouse cursor
  * a scanner line sweeps the head (faster while thinking)
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetricsF, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)

from app.config import UI_PRELOADER
from app.ui.theme import rgba
from app.ui.visualizer import AIVisualizer

INK = "#eaf4ff"
MONO = "Consolas"
EYE = {"idle": "#bfe3ff", "listening": "#ffffff", "thinking": "#ffd166", "speaking": "#9fe3ff"}
SCAN_SPEED = {"idle": 0.5, "listening": 1.2, "thinking": 2.6, "speaking": 1.6}
MARQUEE = "OPTIMUS  ///  LOCAL AI  ///  PRIVATE  ///  OFFLINE FIRST  ///  VOICE  ///  MEMORY  ///  AGENT  ///  "


def _mirror(points):
    return [(-x, y) for x, y in reversed(points)]


# ---- front view geometry (drawing units, roughly -1 to +1)
HELMET = [(-0.60, -0.52), (-0.36, -0.86), (0.36, -0.86), (0.60, -0.52), (0.68, 0.04),
          (0.52, 0.60), (0.24, 0.90), (-0.24, 0.90), (-0.52, 0.60), (-0.68, 0.04)]
CREST = [(-0.15, -0.86), (0.15, -0.86), (0.09, -0.38), (-0.09, -0.38)]
FIN_L = [(-0.68, -0.18), (-0.92, -0.40), (-0.96, 0.16), (-0.68, 0.28)]
FIN_R = _mirror(FIN_L)
VISOR = [(-0.54, -0.26), (0.54, -0.26), (0.44, 0.04), (-0.44, 0.04)]
EYE_L = [(-0.48, -0.21), (-0.09, -0.21), (-0.15, -0.04), (-0.42, -0.04)]
EYE_R = _mirror(EYE_L)
VENT = [(-0.045, 0.06), (0.045, 0.06), (0.07, 0.34), (-0.07, 0.34)]
CHEEK_L = [(-0.54, 0.12), (-0.22, 0.32), (-0.22, 0.76), (-0.42, 0.62)]
CHEEK_R = _mirror(CHEEK_L)
MOUTH = [(-0.24, 0.44), (0.24, 0.44), (0.18, 0.74), (-0.18, 0.74)]
SEAMS = [[(-0.30, -0.80), (-0.24, -0.32)], [(0.30, -0.80), (0.24, -0.32)],
         [(-0.60, -0.52), (-0.54, -0.26)], [(0.60, -0.52), (0.54, -0.26)],
         [(-0.44, 0.04), (-0.52, 0.60)], [(0.44, 0.04), (0.52, 0.60)],
         [(-0.22, 0.76), (-0.24, 0.90)], [(0.22, 0.76), (0.24, 0.90)]]
BOLTS = [(-0.50, -0.45), (0.50, -0.45), (-0.60, 0.0), (0.60, 0.0), (0.0, 0.84)]

# ---- side view geometry
SIDE_DOME = [(-0.50, -0.30), (-0.30, -0.80), (0.10, -0.92), (0.55, -0.70), (0.72, -0.20),
             (0.62, 0.35), (0.30, 0.75), (-0.20, 0.80), (-0.52, 0.45)]
SIDE_BLADE = [(-0.10, -0.92), (-0.30, -1.18), (-0.44, -0.62)]
SIDE_VISOR = [(-0.50, -0.25), (-0.18, -0.20), (-0.16, -0.06), (-0.48, -0.10)]
SIDE_JAW = [(-0.52, 0.45), (-0.45, 0.62), (-0.10, 0.82), (0.30, 0.75)]


def _hair(color, width: float = 1.5) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)           # The same thin line however large the drawing is scaled
    return pen


def _poly(points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def stroke(p, points, t: float, closed: bool = True):
    """Draw a line, revealing it from its start as t goes 0 -> 1 (the 'drawing on' effect)."""
    if t <= 0:
        return
    pts = list(points) + ([points[0]] if closed else [])
    if t >= 1.0:
        p.drawPolyline(_poly(pts))
        return
    lengths = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    remaining = sum(lengths) * t
    out = [pts[0]]
    for (a, b), length in zip(zip(pts, pts[1:]), lengths):
        if remaining >= length:
            out.append(b)
            remaining -= length
        else:
            f = remaining / length if length else 0.0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            break
    p.drawPolyline(_poly(out))


def shape(p, points, t: float, fill: bool = False):
    """Like stroke(), but a finished shape is filled with navy so the grid does not show through."""
    if fill and t >= 1.0:
        p.setBrush(QColor(8, 30, 58, 170))
        p.drawPolygon(_poly(points))
        p.setBrush(Qt.NoBrush)
    else:
        stroke(p, points, t)


class BlueprintVisualizer(AIVisualizer):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        # Negative = wait for the intro curtain to lift before the drawing starts
        self._boot = -1.0 if UI_PRELOADER else 0.0

    def _tick(self):
        super()._tick()
        if self._boot < 1.0:
            self._boot = min(1.0, self._boot + 0.006)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        boot = max(0.0, self._boot)
        phase, amp, state = self._phase, self._amp, self._state

        def stage(a: float, b: float) -> float:        # 0 -> 1 while boot moves from a to b
            return max(0.0, min(1.0, (boot - a) / (b - a)))

        s = max(24.0, min(h * 0.34, w * 0.15))          # Size of the front view
        fcx, fcy = w * 0.50, h * 0.46
        scx, scy, ss = w * 0.83, h * 0.46, s * 0.62     # Side view

        cursor = self.mapFromGlobal(QCursor.pos())      # The details follow the mouse, anywhere on screen
        dx = max(-1.0, min(1.0, (cursor.x() - fcx) / (w * 0.5)))
        dy = max(-1.0, min(1.0, (cursor.y() - fcy) / (h * 0.5)))
        eye_color = QColor(EYE[state])

        if state == "idle":
            glow = 0.55 + 0.12 * math.sin(phase * 1.2)
        elif state == "listening":
            glow = 0.80 + 0.20 * math.sin(phase * 4.0)
        elif state == "thinking":
            glow = 0.85
        else:
            glow = 0.70 + 0.30 * abs(math.sin(phase * 3.0))
        if state == "speaking":
            jaw = abs(math.sin(phase * 3.1)) * (0.45 + 0.55 * abs(math.sin(phase * 1.7)))
        elif state == "listening":
            jaw = 0.12 * abs(math.sin(phase * 2.0))
        else:
            jaw = 0.0

        # ------------------------------------------------------------ front view
        p.save()
        p.translate(fcx, fcy)
        p.scale(s, s)
        p.setBrush(Qt.NoBrush)

        t = stage(0.0, 0.55)
        p.setPen(_hair(rgba(INK, 0.95), 1.6))
        shape(p, HELMET, t, fill=True)
        p.save()                                         # A second, inner outline gives the drafting look
        p.scale(0.93, 0.93)
        p.setPen(_hair(rgba(INK, 0.40), 1.0))
        stroke(p, HELMET, t)
        p.restore()
        p.setPen(_hair(rgba(INK, 0.90), 1.4))
        shape(p, FIN_L, stage(0.10, 0.55), fill=True)
        shape(p, FIN_R, stage(0.10, 0.55), fill=True)
        shape(p, CREST, stage(0.15, 0.60), fill=True)
        p.setPen(_hair(rgba(INK, 0.45), 1.0))
        stroke(p, [(0.0, -0.86), (0.0, -0.38)], stage(0.30, 0.70), closed=False)
        for seam in SEAMS:
            stroke(p, seam, stage(0.40, 0.80), closed=False)

        p.save()                                         # Details shift slightly with the cursor
        p.translate(dx * 0.025, dy * 0.015)
        d = stage(0.30, 0.80)
        p.setPen(_hair(rgba(INK, 0.90), 1.3))
        shape(p, VISOR, d)
        shape(p, CHEEK_L, d)
        shape(p, CHEEK_R, d)
        shape(p, VENT, d)
        p.save()
        p.translate(0, jaw * 0.07)                       # The jaw plate moves with speech
        shape(p, MOUTH, d)
        p.setPen(_hair(rgba(INK, 0.55), 1.0))
        for k in range(4):
            if d >= 1.0:
                y = 0.50 + k * 0.065
                p.drawLine(QPointF(-0.14, y), QPointF(0.14, y))
        p.restore()
        g = glow * stage(0.50, 1.0)
        if g > 0:
            for ex in (-0.285, 0.285):                   # Eye glow
                halo = QRadialGradient(QPointF(ex, -0.125), 0.40)
                halo.setColorAt(0.0, rgba(eye_color, 0.50 * g))
                halo.setColorAt(1.0, rgba(eye_color, 0.0))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(halo))
                p.drawEllipse(QPointF(ex, -0.125), 0.40, 0.40)
            p.setBrush(rgba(eye_color, 0.30 + 0.45 * g))
            p.setPen(_hair(rgba("#ffffff", 0.8 * g), 1.0))
            p.drawPolygon(_poly(EYE_L))
            p.drawPolygon(_poly(EYE_R))
            p.setPen(Qt.NoPen)
            p.setBrush(rgba("#ffffff", min(1.0, g)))     # The pupils follow the cursor
            for ex in (-0.285, 0.285):
                p.drawEllipse(QPointF(ex + dx * 0.05, -0.125 + dy * 0.025), 0.034, 0.034)
        p.restore()

        p.setBrush(Qt.NoBrush)
        if stage(0.60, 0.90) > 0:                        # Rivets
            p.setPen(_hair(rgba(INK, 0.8 * stage(0.60, 0.90)), 1.2))
            for bx, by in BOLTS:
                p.drawEllipse(QPointF(bx, by), 0.02, 0.02)

        if boot > 0.7:                                   # Scanner line, clipped to the helmet
            y = math.sin(phase * SCAN_SPEED[state]) * 0.78
            clip = QPainterPath()
            clip.addPolygon(_poly(HELMET))
            p.save()
            p.setClipPath(clip)
            fade = stage(0.70, 1.0)
            band = QLinearGradient(0, y - 0.10, 0, y + 0.10)
            band.setColorAt(0.0, rgba(eye_color, 0.0))
            band.setColorAt(0.5, rgba(eye_color, 0.28 * fade))
            band.setColorAt(1.0, rgba(eye_color, 0.0))
            p.setPen(Qt.NoPen)
            p.fillRect(QRectF(-0.8, y - 0.10, 1.6, 0.20), QBrush(band))
            p.setPen(_hair(rgba(eye_color, 0.6 * fade), 1.0))
            p.drawLine(QPointF(-0.7, y), QPointF(0.7, y))
            p.restore()
        p.restore()

        # ------------------------------------------------------------ side view
        p.save()
        p.translate(scx, scy)
        p.scale(ss, ss)
        p.setBrush(Qt.NoBrush)
        p.setPen(_hair(rgba(INK, 0.95), 1.6))
        shape(p, SIDE_DOME, stage(0.15, 0.65), fill=True)
        p.setPen(_hair(rgba(INK, 0.90), 1.3))
        shape(p, SIDE_BLADE, stage(0.25, 0.70), fill=True)
        shape(p, SIDE_VISOR, stage(0.35, 0.75))
        stroke(p, SIDE_JAW, stage(0.35, 0.75), closed=False)
        rt = stage(0.40, 0.90)
        if rt > 0:                                       # Concentric receptor rings
            p.setPen(_hair(rgba(INK, 0.9), 1.4))
            for r in (0.28, 0.19, 0.10):
                p.drawArc(QRectF(0.20 - r, 0.02 - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * rt))
            p.setPen(_hair(rgba(INK, 0.45), 1.0))
            stroke(p, [(-0.12, 0.02), (0.52, 0.02)], rt, closed=False)
            stroke(p, [(0.20, -0.30), (0.20, 0.34)], rt, closed=False)
        p.restore()

        # ------------------------------------------------------------ labels, dimensions, callouts
        label = QFont(self.font())
        label.setPixelSize(12)
        label.setBold(True)
        p.setFont(label)
        p.setPen(rgba(INK, 0.90 * stage(0.70, 1.0)))
        p.drawText(QRectF(fcx - 80, fcy + s * 1.20, 160, 20), Qt.AlignCenter, "Front View")
        p.drawText(QRectF(scx - 80, scy + ss * 1.20, 160, 20), Qt.AlignCenter, "Side View")

        dim = stage(0.50, 0.90)                          # Dimension lines with end ticks
        if dim > 0:
            p.setPen(QPen(rgba(INK, 0.55), 1))
            y = fcy + s * 1.06
            stroke(p, [(fcx - s * 0.96, y), (fcx + s * 0.96, y)], dim, closed=False)
            stroke(p, [(fcx - s * 0.96, y - 4), (fcx - s * 0.96, y + 4)], dim, closed=False)
            stroke(p, [(fcx + s * 0.96, y - 4), (fcx + s * 0.96, y + 4)], dim, closed=False)
            x = fcx - s * 1.14
            stroke(p, [(x, fcy - s * 0.90), (x, fcy + s * 0.90)], dim, closed=False)
            stroke(p, [(x - 4, fcy - s * 0.90), (x + 4, fcy - s * 0.90)], dim, closed=False)
            stroke(p, [(x - 4, fcy + s * 0.90), (x + 4, fcy + s * 0.90)], dim, closed=False)

        if w >= 820:                                     # Callout leaders (hidden when the window is narrow)
            ct = stage(0.65, 1.0)
            tiny = QFont(MONO, 8)
            tiny.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            for (sx, sy), (ex, ey), text in (((0.54, -0.12), (1.15, -0.50), "VISOR ARRAY"),
                                              ((0.20, 0.60), (1.15, 0.80), "VOICE PLATE"),
                                              ((0.0, -0.86), (0.55, -1.12), "COMMAND CREST")):
                a = (fcx + sx * s, fcy + sy * s)
                b = (fcx + ex * s, fcy + ey * s)
                c = (fcx + 1.55 * s, b[1])
                p.setPen(_hair(rgba(INK, 0.70), 1.0))
                stroke(p, [a, b, c], ct, closed=False)
                p.setFont(tiny)
                p.setPen(rgba(INK, 0.80 * ct))
                p.drawText(QPointF(c[0] + 6, c[1] + 3), text)

        # ------------------------------------------------------------ left block: status and readouts
        a = stage(0.20, 0.70)
        mono = QFont(MONO, 9)
        mono.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        p.setFont(mono)
        p.setPen(rgba(INK, 0.60 * a))
        p.drawText(QPointF(26, 30), "STATUS  //  01")
        big = QFont(self.font())
        big.setPixelSize(int(max(24, min(42, h * 0.17))))
        big.setBold(True)
        big.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        p.setFont(big)
        p.setPen(rgba(INK, 0.97 * a))
        p.drawText(QRectF(26, 40, w * 0.30, 56), Qt.AlignLeft | Qt.AlignVCenter, self.STATES[state][2])
        p.setFont(mono)
        p.setPen(rgba(INK, 0.55 * a))
        for i, text in enumerate((f"AMP    {amp:0.2f}", f"SPEED  {self._speed:0.1f}x", "TRACK  CURSOR")):
            p.drawText(QPointF(26, 106 + i * 14), text)
        sa = stage(0.50, 1.0)
        if sa > 0:                                       # A small oscilloscope
            x0, width, ys = 26.0, w * 0.26, h - 40.0
            points = [QPointF(x0 + width * i / 47,
                              ys + math.sin(i * 0.55 + phase * 3.0) * math.sin(i * 0.13 + 0.5) * amp * 16.0)
                      for i in range(48)]
            p.setPen(QPen(rgba(INK, 0.20 * sa), 1))
            p.drawLine(QPointF(x0, ys), QPointF(x0 + width, ys))
            p.setPen(QPen(rgba(INK, 0.80 * sa), 1.2))
            p.drawPolyline(QPolygonF(points))

        marquee = QFont(MONO, 8)                         # Slowly scrolling microcopy (faster while speaking)
        marquee.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        p.setFont(marquee)
        p.setPen(rgba(INK, 0.28))
        unit = QFontMetricsF(marquee).horizontalAdvance(MARQUEE)
        if unit > 0:
            x = -((phase * 22.0) % unit)
            while x < w:
                p.drawText(QPointF(x, h - 7), MARQUEE)
                x += unit


# --- end of file ---