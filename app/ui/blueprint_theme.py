"""
Blueprint theme: a technical-drawing interface (navy sheet, white hairline ink).

apply_blueprint_theme() must run BEFORE the main window is created. It
  * switches the colour palette (the whole app follows, because every widget reads Colors),
  * repaints GlassPanel and BackgroundWidget as drawing sheets (grid, frame, ticks, corner marks),
  * swaps the orb for the animated schematic and the logo for a line-art one,
  * adds the intro preloader,
  * returns (font family, extra stylesheet) for main.py.
All artwork is original and drawn in code.
"""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)

from app.config import UI_PRELOADER
from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.theme import FONT_FAMILY, Colors, rgba

INK = "#eaf4ff"
PALETTE = {
    "BG_TOP": "#0c2a4d", "BG_BOTTOM": "#071b34", "PANEL": "#0e2b50",
    "ACCENT": "#4aa3ff", "ACCENT_LIGHT": "#9fd0ff", "ACCENT_DEEP": "#1b5fb0",
    "ACCENT_CYAN": "#bfe3ff", "TEXT": "#eaf4ff", "TEXT_DIM": "#8fb0d6",
}
QSS = """
QLabel { color: #eaf4ff; }
QLabel#SectionLabel, QLabel#Tagline, QLabel#Footer, QLabel#StatusText, QLabel#BubbleTime, QLabel#SettingDesc { font-family: Consolas; }
QPushButton#PrimaryButton { background: transparent; color: #eaf4ff; border: 1px solid #eaf4ff; border-radius: 0px; padding: 11px 14px; font-family: Consolas; font-size: 12px; font-weight: 600; }
QPushButton#PrimaryButton:hover { background: #eaf4ff; color: #0a2444; }
QPushButton#PrimaryButton:pressed { background: #9fd0ff; color: #0a2444; }
QLineEdit#ChatInput { font-family: Consolas; font-size: 15px; selection-background-color: #4aa3ff; }
QFrame#UserBubble { background: rgba(74, 163, 255, 46); border: 1px solid rgba(159, 208, 255, 200); border-top-left-radius: 0px; border-top-right-radius: 0px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }
QFrame#AssistantBubble { background: rgba(255, 255, 255, 10); border: 1px solid rgba(234, 244, 255, 110); border-top-left-radius: 0px; border-top-right-radius: 0px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }
QListWidget#HistoryList::item { border-radius: 0px; border: none; border-bottom: 1px solid rgba(234, 244, 255, 34); }
QListWidget#HistoryList::item:selected { background: rgba(74, 163, 255, 46); border: none; border-left: 3px solid #eaf4ff; border-bottom: 1px solid rgba(234, 244, 255, 34); }
QScrollBar::handle:vertical { background: rgba(234, 244, 255, 90); border-radius: 0px; }
"""
_applied = False
_family = FONT_FAMILY
_noise = None


def _noise_brush() -> QBrush:
    """A tiny film-grain tile, created once and repeated over the whole sheet."""
    global _noise
    if _noise is None:
        rng = np.random.default_rng(7)
        data = np.zeros((128, 128, 4), dtype=np.uint8)
        data[..., :3] = 255
        data[..., 3] = rng.integers(0, 16, size=(128, 128), dtype=np.uint8)
        _noise = QPixmap.fromImage(QImage(data.data, 128, 128, 128 * 4, QImage.Format_ARGB32).copy())
    return QBrush(_noise)


def _render_background(w: int, h: int, dpr: float) -> QPixmap:
    """The drawing sheet. Painted once per window size, then reused (almost free per frame)."""
    pixmap = QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    p = QPainter(pixmap)
    area = QRectF(0, 0, w, h)
    iw, ih = int(w), int(h)
    base = QLinearGradient(0, 0, 0, h)
    base.setColorAt(0.0, QColor(Colors.BG_TOP))
    base.setColorAt(1.0, QColor(Colors.BG_BOTTOM))
    p.fillRect(area, QBrush(base))

    p.setPen(QPen(QColor(111, 163, 224, 24), 1))              # Fine grid every 16 px
    for x in range(0, iw + 1, 16):
        p.drawLine(x, 0, x, ih)
    for y in range(0, ih + 1, 16):
        p.drawLine(0, y, iw, y)
    p.setPen(QPen(QColor(150, 195, 245, 54), 1))              # Heavier grid every 5th line
    for x in range(0, iw + 1, 80):
        p.drawLine(x, 0, x, ih)
    for y in range(0, ih + 1, 80):
        p.drawLine(0, y, iw, y)

    vignette = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.75)
    vignette.setColorAt(0.55, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 8, 20, 150))
    p.fillRect(area, QBrush(vignette))

    inset = 9                                                 # Drawing frame with edge ticks
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(234, 244, 255, 100), 1))
    p.drawRect(inset, inset, iw - 2 * inset, ih - 2 * inset)
    for x in range(inset + 40, iw - inset, 40):
        p.drawLine(x, inset, x, inset + 5)
        p.drawLine(x, ih - inset, x, ih - inset - 5)
    for y in range(inset + 40, ih - inset, 40):
        p.drawLine(inset, y, inset + 5, y)
        p.drawLine(iw - inset, y, iw - inset - 5, y)
    p.setPen(QPen(QColor(234, 244, 255, 190), 1))             # Corner crosshairs
    for x, y in ((inset, inset), (iw - inset, inset), (inset, ih - inset), (iw - inset, ih - inset)):
        p.drawLine(x - 7, y, x + 7, y)
        p.drawLine(x, y - 7, x, y + 7)

    p.fillRect(area, _noise_brush())                          # Film grain
    p.end()
    return pixmap


def _background_paint(self, event):
    key = (self.width(), self.height(), self.devicePixelRatioF())
    if getattr(self, "_bp_key", None) != key:
        self._bp_pixmap = _render_background(*key)
        self._bp_key = key
    QPainter(self).drawPixmap(0, 0, self._bp_pixmap)


def _panel_paint(self, event):
    """A drawing frame: navy glass, hairline border, dashed inner frame, corner marks, ruler ticks."""
    p = QPainter(self)
    r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    p.fillRect(r, QColor(10, 36, 68, int(255 * min(0.92, self._tint + 0.10))))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(rgba(INK, 0.55), 1))
    p.drawRect(r)
    p.setPen(QPen(rgba(INK, 0.16), 1, Qt.DashLine))
    p.drawRect(r.adjusted(5, 5, -5, -5))
    p.setPen(QPen(rgba(INK, 0.95), 2))
    length = 14
    for x, y, sx, sy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                         (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + sx * length, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + sy * length))
    p.setPen(QPen(rgba(INK, 0.35), 1))                        # Ruler ticks along the top edge
    for i, x in enumerate(range(int(r.left()) + 28, int(r.right()) - 28, 12)):
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.top() + (6 if i % 5 == 0 else 3)))


def _logo_paint(self, event):
    """Line-art logo: a crosshair-in-circle emblem and an outlined OPTIMUS wordmark."""
    p = QPainter(self)
    p.setRenderHint(QPainter.Antialiasing)
    cy = self.height() / 2
    center = QPointF(22, cy)
    ink = QColor(INK)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(ink, 1.4))
    p.drawEllipse(center, 12, 12)
    p.drawEllipse(center, 6, 6)
    p.drawLine(QPointF(4, cy), QPointF(40, cy))
    p.drawLine(QPointF(22, cy - 18), QPointF(22, cy + 18))
    font = QFont(_family, 17)
    font.setBold(True)
    metrics = QFontMetricsF(font)
    x = 54.0
    baseline = cy + (metrics.ascent() - metrics.descent()) / 2
    path = QPainterPath()
    for ch in "OPTIMUS":
        path.addText(QPointF(x, baseline), font, ch)
        x += metrics.horizontalAdvance(ch) + 3.5
    p.setPen(QPen(ink, 1.1))
    p.drawPath(path)


def apply_blueprint_theme():
    """Call once, after QApplication exists and before the main window is created.
    Returns (font family, extra stylesheet)."""
    global _applied, _family
    _family = "Bahnschrift" if "Bahnschrift" in QFontDatabase.families() else FONT_FAMILY
    if not _applied:
        from app.ui.blueprint_head import BlueprintVisualizer
        from app.ui.sidebar import BrandLogo
        import app.ui.main_window as main_window        # It looks up AIVisualizer when it builds the window
        for name, value in PALETTE.items():
            setattr(Colors, name, value)
        GlassPanel.paintEvent = _panel_paint
        BackgroundWidget.paintEvent = _background_paint
        BrandLogo.paintEvent = _logo_paint
        main_window.AIVisualizer = BlueprintVisualizer
        if UI_PRELOADER:
            from app.ui.preloader import PreloaderOverlay
            original = main_window.MainWindow.showEvent

            def show_event(self, event):
                original(self, event)
                if not getattr(self, "_preloader_started", False):
                    self._preloader_started = True
                    PreloaderOverlay(self.central, _family).start()

            main_window.MainWindow.showEvent = show_event
        _applied = True
    return _family, QSS


# --- end of file ---