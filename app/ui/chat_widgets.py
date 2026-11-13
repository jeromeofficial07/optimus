"""
Chat widgets:

MessageBubble   - one chat message (user or assistant) with a timestamp.
TypingIndicator - three bouncing dots shown while the assistant is "thinking".
ChatView        - the scrolling conversation area that holds all bubbles.
"""
import math
from datetime import datetime

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QPointF,
                            QPropertyAnimation, QRectF, Qt, QTimer)
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from app.ui.theme import Colors, rgba


class MessageBubble(QFrame):
    """A single chat bubble. role is 'user' or 'assistant'."""

    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.role = role
        # The object name selects the matching style in theme.py
        self.setObjectName("UserBubble" if role == "user" else "AssistantBubble")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("BubbleText")
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # Allow copying
        self.text_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self.time_label = QLabel(datetime.now().strftime("%H:%M"))
        self.time_label.setObjectName("BubbleTime")
        self.time_label.setAlignment(Qt.AlignRight if role == "user" else Qt.AlignLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(4)
        layout.addWidget(self.text_label)
        layout.addWidget(self.time_label)

        self.set_font_px(15)

    def set_font_px(self, px: int):
        """Change the message text size (pixels)."""
        font = self.text_label.font()
        font.setPixelSize(px)
        self.text_label.setFont(font)

    def set_timestamp_visible(self, visible: bool):
        self.time_label.setVisible(visible)


class TypingIndicator(QWidget):
    """A small pill with three dots that bounce one after another."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 34)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event):   # Only animate while visible
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        self._t = (self._t + 0.025) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pill = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(rgba(Colors.ACCENT_LIGHT, 0.28), 1))
        painter.setBrush(rgba("#ffffff", 0.07))
        painter.drawRoundedRect(pill, 17, 17)

        painter.setPen(Qt.NoPen)
        for i in range(3):
            # Each dot is delayed slightly compared with the previous one
            lift = max(0.0, math.sin((self._t - i * 0.15) * 2 * math.pi))
            painter.setBrush(rgba(Colors.ACCENT_LIGHT, 0.4 + 0.6 * lift))
            painter.drawEllipse(QPointF(20 + i * 12, 17 - 5 * lift), 3.2, 3.2)


class ChatView(QScrollArea):
    """Scrollable list of message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatScroll")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._container.setObjectName("ChatContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(18, 18, 18, 18)
        self._layout.setSpacing(14)
        self._layout.addStretch(1)  # Always the LAST item; messages go before it
        self.setWidget(self._container)

        # Make the scroll area see-through so the glass panel shows behind it
        self._container.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)

        self._bubbles: list[MessageBubble] = []
        self._typing_row: QWidget | None = None
        self._show_timestamps = True
        self._font_px = 15

        # Reusable animation for smooth scrolling
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(320)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ----- helpers -----
    def _bubble_max_width(self) -> int:
        """Bubbles take at most ~78% of the visible width, so they adapt on resize."""
        return max(240, int(self.viewport().width() * 0.78))

    def _insert_index(self) -> int:
        """Where to put a new row: before the typing dots (if shown) or the end stretch."""
        if self._typing_row is not None:
            return self._layout.indexOf(self._typing_row)
        return self._layout.count() - 1

    def _fade_in(self, widget: QWidget):
        """Fade a widget from invisible to visible."""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Remove the effect afterwards; it is no longer needed and costs performance
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    # ----- public API -----
    def add_message(self, role: str, text: str, animate: bool = True) -> MessageBubble:
        """Add a bubble. User bubbles align right, assistant bubbles align left."""
        bubble = MessageBubble(role, text)
        bubble.set_font_px(self._font_px)
        bubble.set_timestamp_visible(self._show_timestamps)
        bubble.setMaximumWidth(self._bubble_max_width())

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)

        self._layout.insertWidget(self._insert_index(), row)
        self._bubbles.append(bubble)
        if animate:
            self._fade_in(row)
        QTimer.singleShot(80, self.scroll_to_bottom)  # Wait for layout, then scroll
        return bubble

    def show_typing(self):
        """Show the bouncing dots as if the assistant is composing a reply."""
        if self._typing_row is not None:
            return
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(TypingIndicator())
        row_layout.addStretch(1)
        self._layout.insertWidget(self._layout.count() - 1, row)
        self._typing_row = row
        QTimer.singleShot(80, self.scroll_to_bottom)

    def hide_typing(self):
        if self._typing_row is None:
            return
        self._layout.removeWidget(self._typing_row)
        self._typing_row.deleteLater()
        self._typing_row = None

    def clear(self):
        """Remove every message (used by 'New conversation')."""
        while self._layout.count() > 1:  # Keep the final stretch item
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._bubbles.clear()
        self._typing_row = None

    def scroll_to_bottom(self):
        """Smoothly scroll to the newest message."""
        bar = self.verticalScrollBar()
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(bar.maximum())
        self._scroll_anim.start()

    def set_timestamps_visible(self, visible: bool):
        self._show_timestamps = visible
        for bubble in self._bubbles:
            bubble.set_timestamp_visible(visible)

    def set_font_size(self, px: int):
        self._font_px = px
        for bubble in self._bubbles:
            bubble.set_font_px(px)

    def resizeEvent(self, event):
        """Keep bubble widths proportional when the window is resized."""
        super().resizeEvent(event)
        max_width = self._bubble_max_width()
        for bubble in self._bubbles:
            bubble.setMaximumWidth(max_width)