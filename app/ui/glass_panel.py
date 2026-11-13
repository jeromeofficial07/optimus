"""
Glass-style container widgets.

GlassPanel      - a rounded, tinted, semi-transparent panel with a light border.
BackgroundWidget - the dark gradient backdrop with soft blue glows that the
                   glass panels sit on. The glows are what make the glass visible.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget

from app.ui.theme import Colors, rgba


class GlassPanel(QFrame):
    """A frosted-glass looking rounded panel. Put other widgets inside it with a layout."""

    def __init__(self, radius: int = 22, tint: float = 0.55, parent=None):
        super().__init__(parent)
        self._radius = radius  # Corner radius in pixels
        self._tint = tint      # Opacity (0-1) of the dark base colour

    def paintEvent(self, event):
        """Draw three layers: dark tint, light sheen, then a gradient border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = self._radius

        # Layer 1: translucent dark base
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(Colors.PANEL, self._tint))
        painter.drawRoundedRect(rect, r, r)

        # Layer 2: diagonal sheen (brighter at the top-left, like light on glass)
        sheen = QLinearGradient(rect.topLeft(), rect.bottomRight())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(0.5, QColor(255, 255, 255, 6))
        sheen.setColorAt(1.0, QColor(96, 165, 250, 14))
        painter.setBrush(sheen)
        painter.drawRoundedRect(rect, r, r)

        # Layer 3: thin gradient border
        border = QLinearGradient(rect.topLeft(), rect.bottomRight())
        border.setColorAt(0.0, QColor(255, 255, 255, 70))
        border.setColorAt(0.5, QColor(96, 165, 250, 35))
        border.setColorAt(1.0, QColor(96, 165, 250, 70))
        painter.setPen(QPen(QBrush(border), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, r, r)


class BackgroundWidget(QWidget):
    """Window backdrop: dark gradient plus soft glowing colour blobs."""

    resized = Signal()  # Emitted on every resize so the main window can react

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        # Base vertical gradient
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.0, QColor(Colors.BG_TOP))
        base.setColorAt(1.0, QColor(Colors.BG_BOTTOM))
        painter.fillRect(self.rect(), base)

        # Soft glows (centre, radius, colour, strength)
        big = max(w, h)
        self._glow(painter, QPointF(w * 0.15, h * 0.05), big * 0.60, Colors.ACCENT, 0.26)
        self._glow(painter, QPointF(w * 0.95, h * 0.95), big * 0.55, Colors.ACCENT_DEEP, 0.30)
        self._glow(painter, QPointF(w * 0.70, h * 0.25), big * 0.35, Colors.ACCENT_CYAN, 0.07)

    def _glow(self, painter, center, radius, color, alpha):
        """Fill the whole widget with a radial gradient that fades to transparent."""
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, rgba(color, alpha))
        gradient.setColorAt(1.0, rgba(color, 0.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRect(self.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()