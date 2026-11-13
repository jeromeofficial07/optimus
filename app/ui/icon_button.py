"""
IconButton - a round button whose icon is painted in code (no image files needed).

Supported icons: mic, send, gear, plus, menu, close.
Hovering fades the button smoothly using an animated 'hover' property.
"""
import math

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation,
                            QRectF, Qt)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton

from app.ui.theme import Colors, mix, rgba


class IconButton(QPushButton):
    def __init__(self, kind: str, size: int = 44, tooltip: str = "",
                 checkable: bool = False, filled: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind        # Which icon to draw
        self._filled = filled    # True = solid accent-gradient button (used for Send)
        self._hover = 0.0        # 0.0 (idle) to 1.0 (hovered); animated

        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(checkable)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.NoFocus)  # Keep keyboard focus in the text field

        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ----- animated property -----
    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float):
        self._hover = value
        self.update()  # Repaint with the new value

    hover = Property(float, _get_hover, _set_hover)

    def _animate_to(self, target: float):
        """Smoothly move the hover value to the target."""
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(0.0)
        super().leaveEvent(event)

    def set_kind(self, kind: str):
        """Swap the icon (for example mic -> stop later)."""
        self._kind = kind
        self.update()

    # ----- painting -----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isDown():
            rect = rect.adjusted(1.5, 1.5, -1.5, -1.5)  # Slight press-in effect
        h = self._hover

        if self._filled:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, mix(Colors.ACCENT, Colors.ACCENT_LIGHT, h))
            gradient.setColorAt(1.0, mix(Colors.ACCENT_DEEP, Colors.ACCENT, h))
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(rect)
            icon_color = QColor("white")
        else:
            if self.isChecked():
                fill = rgba(Colors.ACCENT, 0.28)
                border = rgba(Colors.ACCENT_LIGHT, 0.9)
                icon_color = QColor(Colors.ACCENT_LIGHT)
            else:
                fill = QColor(255, 255, 255, int(255 * (0.05 + 0.09 * h)))
                border = rgba(Colors.ACCENT_LIGHT, 0.12 + 0.35 * h)
                icon_color = mix(Colors.TEXT_DIM, Colors.TEXT, h)
            painter.setPen(QPen(border, 1.2))
            painter.setBrush(fill)
            painter.drawEllipse(rect)

        # Icons are drawn in a -12..+12 coordinate space, centred and scaled to fit.
        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        scale = min(self.width(), self.height()) / 40.0
        painter.scale(scale, scale)
        pen = QPen(icon_color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        drawer = getattr(self, f"_draw_{self._kind}", None)
        if drawer:
            drawer(painter, icon_color)
        painter.restore()

    # ----- icon drawings -----
    def _draw_mic(self, p, color):
        p.drawRoundedRect(QRectF(-3.5, -10, 7, 13), 3.5, 3.5)   # capsule
        p.drawArc(QRectF(-7, -6, 14, 14), 180 * 16, 180 * 16)   # U-shaped holder
        p.drawLine(QPointF(0, 8), QPointF(0, 11))                # stem
        p.drawLine(QPointF(-3.5, 11), QPointF(3.5, 11))          # base

    def _draw_send(self, p, color):
        path = QPainterPath()
        path.moveTo(-9, -8)
        path.lineTo(10, 0)
        path.lineTo(-9, 8)
        path.lineTo(-5, 0)
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)

    def _draw_gear(self, p, color):
        p.drawEllipse(QPointF(0, 0), 5.5, 5.5)
        p.drawEllipse(QPointF(0, 0), 2, 2)
        for i in range(8):  # 8 teeth around the ring
            a = math.radians(i * 45)
            p.drawLine(QPointF(8 * math.cos(a), 8 * math.sin(a)),
                       QPointF(10.5 * math.cos(a), 10.5 * math.sin(a)))

    def _draw_plus(self, p, color):
        p.drawLine(QPointF(-8, 0), QPointF(8, 0))
        p.drawLine(QPointF(0, -8), QPointF(0, 8))

    def _draw_menu(self, p, color):
        for y in (-7, 0, 7):
            p.drawLine(QPointF(-9, y), QPointF(9, y))

    def _draw_close(self, p, color):
        p.drawLine(QPointF(-7, -7), QPointF(7, 7))
        p.drawLine(QPointF(-7, 7), QPointF(7, -7))