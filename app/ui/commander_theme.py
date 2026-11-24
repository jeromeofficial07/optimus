"""
Commander theme: a robotic, animated red / blue / steel interface.

apply_commander_theme() must run BEFORE the main window is created. It
  * switches the colour palette (the whole app follows, because every widget reads Colors),
  * replaces how GlassPanel and BackgroundWidget are painted (armoured steel panels, hex-grid backdrop),
  * swaps the orb for CommanderVisualizer (the animated robot head in commander_head.py).
All artwork is original and drawn in code.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)

from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.theme import FONT_FAMILY, Colors, rgba

PALETTE = {
    "BG_TOP": "#06080f", "BG_BOTTOM": "#0c1322", "PANEL": "#101a30",
    "ACCENT": "#e5383b", "ACCENT_LIGHT": "#ff6b6b", "ACCENT_DEEP": "#9b1c24",
    "ACCENT_CYAN": "#3aa7ff", "TEXT": "#e8eef9", "TEXT_DIM": "#8d9bb5",
}
_applied = False


# ====================================================================== armoured panels
def _panel_paint(self, event):
    painter = QPainter(self)
    painter.setRenderHint(QPainter.Antialiasing)
    r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
    c = min(20.0, max(8.0, self._radius * 0.7))   # Size of the cut corners

    path = QPainterPath(QPointF(r.left() + c, r.top()))   # Cut corners: top-left and bottom-right
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom() - c)
    path.lineTo(r.right() - c, r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + c)
    path.closeSubpath()

    alpha = self._tint + 0.12
    fill = QLinearGradient(r.topLeft(), r.bottomRight())
    fill.setColorAt(0.0, rgba("#22305a", alpha))
    fill.setColorAt(0.5, rgba("#141e38", alpha))
    fill.setColorAt(1.0, rgba("#0b1224", alpha))
    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
    painter.drawPath(path)

    sheen = QLinearGradient(0, r.top(), 0, r.top() + max(1.0, r.height() * 0.35))   # Light on the top edge
    sheen.setColorAt(0.0, QColor(255, 255, 255, 24))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(sheen)
    painter.drawPath(path)

    edge = QLinearGradient(r.topLeft(), r.bottomRight())     # Bevelled metal edge
    edge.setColorAt(0.0, QColor(170, 190, 230, 130))
    edge.setColorAt(1.0, QColor(70, 90, 140, 130))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QBrush(edge), 1.3))
    painter.drawPath(path)

    red, blue = QColor(Colors.ACCENT), QColor(Colors.ACCENT_CYAN)
    red.setAlpha(230)
    blue.setAlpha(230)
    painter.setPen(QPen(red, 3.0))                                    # Label tab
    painter.drawLine(QPointF(r.left() + c + 10, r.top()), QPointF(r.left() + c + 58, r.top()))
    painter.setPen(QPen(red, 2.0))                                    # Lit cut corners
    painter.drawLine(QPointF(r.left(), r.top() + c), QPointF(r.left() + c, r.top()))
    painter.setPen(QPen(blue, 2.0))
    painter.drawLine(QPointF(r.right(), r.bottom() - c), QPointF(r.right() - c, r.bottom()))
    painter.drawLine(QPointF(r.right() - 22, r.top()), QPointF(r.right(), r.top()))      # Corner brackets
    painter.drawLine(QPointF(r.right(), r.top()), QPointF(r.right(), r.top() + 22))
    painter.setPen(QPen(red, 2.0))
    painter.drawLine(QPointF(r.left(), r.bottom() - 22), QPointF(r.left(), r.bottom()))
    painter.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.left() + 22, r.bottom()))

    painter.setPen(Qt.NoPen)                                          # Rivets
    for x, y in ((r.right() - 10, r.top() + 10), (r.left() + 10, r.bottom() - 10)):
        painter.setBrush(QColor(150, 170, 210, 90))
        painter.drawEllipse(QPointF(x, y), 2.4, 2.4)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawEllipse(QPointF(x - 0.7, y - 0.7), 0.9, 0.9)


# ====================================================================== backdrop
def _hex_grid(w: float, h: float, r: float = 26.0) -> QPainterPath:
    path = QPainterPath()
    dx, dy = r * 1.5, r * math.sqrt(3)
    column, x = 0, -r
    while x < w + r:
        y = -dy + (dy / 2 if column % 2 else 0)
        while y < h + dy:
            for k in range(6):
                a1, a2 = math.radians(60 * k), math.radians(60 * (k + 1))
                path.moveTo(x + r * math.cos(a1), y + r * math.sin(a1))
                path.lineTo(x + r * math.cos(a2), y + r * math.sin(a2))
            y += dy
        x += dx
        column += 1
    return path


def _render_background(w: int, h: int, dpr: float) -> QPixmap:
    """Painted once per window size, then reused, so the backdrop costs almost nothing per frame."""
    pixmap = QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    area = QRectF(0, 0, w, h)
    base = QLinearGradient(0, 0, 0, h)
    base.setColorAt(0.0, QColor(Colors.BG_TOP))
    base.setColorAt(1.0, QColor(Colors.BG_BOTTOM))
    painter.fillRect(area, QBrush(base))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(rgba(Colors.ACCENT_CYAN, 0.07), 1))
    painter.drawPath(_hex_grid(w, h))
    big = max(w, h)
    for center, radius, color, alpha in ((QPointF(w * 0.08, h * 0.05), big * 0.55, Colors.ACCENT, 0.22),
                                         (QPointF(w * 0.95, h * 0.95), big * 0.60, Colors.ACCENT_CYAN, 0.20)):
        glow = QRadialGradient(center, radius)
        glow.setColorAt(0.0, rgba(color, alpha))
        glow.setColorAt(1.0, rgba(color, 0.0))
        painter.fillRect(area, QBrush(glow))
    painter.setPen(QPen(QColor(0, 0, 0, 38), 1))                      # Scanlines
    for y in range(0, int(h), 3):
        painter.drawLine(0, y, int(w), y)
    painter.end()
    return pixmap


def _background_paint(self, event):
    key = (self.width(), self.height(), self.devicePixelRatioF())
    if getattr(self, "_cmd_key", None) != key:
        self._cmd_pixmap = _render_background(*key)
        self._cmd_key = key
    painter = QPainter(self)
    painter.drawPixmap(0, 0, self._cmd_pixmap)


# ====================================================================== switch it on
def apply_commander_theme() -> str:
    """Call once, after QApplication exists and before the main window is created.
    Returns the font family to use for the application."""
    global _applied
    if not _applied:
        from app.ui.commander_head import CommanderVisualizer
        for name, value in PALETTE.items():
            setattr(Colors, name, value)
        GlassPanel.paintEvent = _panel_paint
        BackgroundWidget.paintEvent = _background_paint
        import app.ui.main_window as main_window        # It looks up AIVisualizer when it builds the window
        main_window.AIVisualizer = CommanderVisualizer
        _applied = True
    return "Bahnschrift" if "Bahnschrift" in QFontDatabase.families() else FONT_FAMILY


# --- end of file ---