"""
Sidebar - branding, 'New conversation' button and the conversation history list.
History items are placeholders for now; real ones come from SQLite later.
"""
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from app.config import APP_VERSION
from app.ui.glass_panel import GlassPanel
from app.ui.theme import FONT_FAMILY, Colors, rgba


class BrandLogo(QWidget):
    """Glowing ring emblem and a gradient 'OPTIMUS' wordmark, painted in code."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        center = QPointF(22, cy)

        # Emblem: glow, ring, centre dot
        glow = QRadialGradient(center, 22)
        glow.setColorAt(0.0, rgba(Colors.ACCENT, 0.40))
        glow.setColorAt(1.0, rgba(Colors.ACCENT, 0.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, 22, 22)
        painter.setPen(QPen(QColor(Colors.ACCENT_LIGHT), 2.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, 11, 11)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Colors.ACCENT_CYAN))
        painter.drawEllipse(center, 4, 4)

        # Wordmark: draw letter by letter so we control the spacing
        font = QFont(FONT_FAMILY, 17)
        font.setBold(True)
        metrics = QFontMetricsF(font)
        x = 50.0
        baseline = cy + (metrics.ascent() - metrics.descent()) / 2
        path = QPainterPath()
        for ch in "OPTIMUS":
            path.addText(QPointF(x, baseline), font, ch)
            x += metrics.horizontalAdvance(ch) + 3.5
        gradient = QLinearGradient(50, 0, x, 0)
        gradient.setColorAt(0.0, QColor("#e0f2fe"))
        gradient.setColorAt(1.0, QColor(Colors.ACCENT_LIGHT))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)


class Sidebar(GlassPanel):
    new_chat_requested = Signal()
    conversation_selected = Signal(str)  # Emits the conversation title

    def __init__(self, parent=None):
        super().__init__(radius=26, tint=0.6, parent=parent)
        self.setFixedWidth(272)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 18, 16)
        layout.setSpacing(12)

        tagline = QLabel("Intelligent Personal Assistant")
        tagline.setObjectName("Tagline")

        self.new_button = QPushButton("+   New conversation")
        self.new_button.setObjectName("PrimaryButton")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.clicked.connect(self.new_chat_requested)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)

        section = QLabel("CONVERSATION HISTORY")
        section.setObjectName("SectionLabel")

        self.history = QListWidget()
        self.history.setObjectName("HistoryList")
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history.setFocusPolicy(Qt.NoFocus)
        self.history.itemClicked.connect(lambda item: self.conversation_selected.emit(item.text()))

        footer = QLabel(f"v{APP_VERSION}  ·  Interface preview")
        footer.setObjectName("Footer")

        layout.addWidget(BrandLogo())
        layout.addWidget(tagline)
        layout.addSpacing(6)
        layout.addWidget(self.new_button)
        layout.addWidget(divider)
        layout.addWidget(section)
        layout.addWidget(self.history, 1)
        layout.addWidget(footer)

        # Placeholder history so you can see the list styling
        self.set_history(["Welcome to OPTIMUS", "Project ideas", "Study plan"])

    def set_history(self, titles: list[str]):
        """Replace the whole list."""
        self.history.clear()
        self.history.addItems(titles)

    def add_conversation(self, title: str):
        """Insert a conversation at the top and highlight it (skips duplicates at the top)."""
        top = self.history.item(0)
        if top is not None and top.text() == title:
            self.history.setCurrentRow(0)
            return
        self.history.insertItem(0, title)
        self.history.setCurrentRow(0)