"""
Visual theme for OPTIMUS.

Holds the colour palette, small colour helpers and the global Qt stylesheet
(QSS, which is like CSS for Qt widgets). Every other UI file imports colours
from here so the look can be changed in one place.
"""
from string import Template

from PySide6.QtGui import QColor

FONT_FAMILY = "Segoe UI"  # Default Windows 11 font


class Colors:
    """The OPTIMUS colour palette (hex strings)."""
    BG_TOP = "#04060d"
    BG_BOTTOM = "#0a1230"
    PANEL = "#0b1226"
    ACCENT = "#3b82f6"
    ACCENT_LIGHT = "#60a5fa"
    ACCENT_DEEP = "#1d4ed8"
    ACCENT_CYAN = "#22d3ee"
    TEXT = "#e6ecff"
    TEXT_DIM = "#8a96b8"
    SUCCESS = "#34d399"
    WARNING = "#fbbf24"
    DANGER = "#f87171"


def rgba(color, alpha: float) -> QColor:
    """Return a QColor from a hex string or QColor with the given alpha (0.0 to 1.0)."""
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def mix(color_a, color_b, t: float) -> QColor:
    """Blend two colours. t=0 gives color_a, t=1 gives color_b."""
    a, b = QColor(color_a), QColor(color_b)
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def qss_rgba(color, alpha: float) -> str:
    """Return a colour as a stylesheet 'rgba(r, g, b, a)' string (alpha 0 to 255)."""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


# ${NAME} placeholders are filled in by build_stylesheet() below.
_QSS = """
QToolTip {
    background-color: #0f1a3a;
    color: ${TEXT};
    border: 1px solid ${ACCENT_DEEP};
    padding: 6px 8px;
    border-radius: 6px;
}

QLabel { color: ${TEXT}; background: transparent; }
QLabel#SectionLabel { color: ${TEXT_DIM}; font-size: 10px; font-weight: 600; }
QLabel#Tagline { color: ${TEXT_DIM}; font-size: 11px; }
QLabel#Footer { color: ${TIME_DIM}; font-size: 10px; }
QLabel#StatusText { color: ${TEXT_DIM}; font-size: 12px; }
QLabel#PanelTitle { font-size: 18px; font-weight: 600; }
QLabel#SettingTitle { font-size: 13px; font-weight: 600; }
QLabel#SettingDesc { color: ${TEXT_DIM}; font-size: 11px; }
QLabel#BubbleText { color: ${TEXT}; background: transparent; }
QLabel#BubbleTime { color: ${TIME_DIM}; font-size: 10px; background: transparent; }

QFrame#Divider { background: ${DIVIDER}; border: none; }

QLineEdit#ChatInput {
    background: transparent;
    border: none;
    color: ${TEXT};
    font-size: 15px;
    padding: 6px 4px;
    selection-background-color: ${ACCENT_DEEP};
}

QPushButton#PrimaryButton {
    color: white;
    font-size: 13px;
    font-weight: 600;
    border: none;
    border-radius: 12px;
    padding: 11px 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 ${ACCENT}, stop:1 ${ACCENT_DEEP});
}
QPushButton#PrimaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 ${ACCENT_LIGHT}, stop:1 ${ACCENT});
}
QPushButton#PrimaryButton:pressed { background: ${ACCENT_DEEP}; }

QListWidget#HistoryList { background: transparent; border: none; outline: none; }
QListWidget#HistoryList::item {
    color: ${TEXT_DIM};
    padding: 10px 12px;
    margin: 2px 0;
    border-radius: 10px;
    border: 1px solid transparent;
}
QListWidget#HistoryList::item:hover { background: ${HOVER}; color: ${TEXT}; }
QListWidget#HistoryList::item:selected {
    background: ${SELECTED};
    color: ${TEXT};
    border: 1px solid ${SELECTED_BORDER};
}

QScrollArea#ChatScroll { background: transparent; border: none; }
QWidget#qt_scrollarea_viewport { background: transparent; }
QWidget#ChatContainer { background: transparent; }

QFrame#UserBubble {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2f6df0, stop:1 #1d4ed8);
    border: 1px solid rgba(147, 197, 253, 90);
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
    border-bottom-left-radius: 18px;
    border-bottom-right-radius: 5px;
}
QFrame#AssistantBubble {
    background: ${ASSIST_BG};
    border: 1px solid ${ASSIST_BORDER};
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
    border-bottom-left-radius: 5px;
    border-bottom-right-radius: 18px;
}

QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 0; }
QScrollBar::handle:vertical { background: ${SCROLL}; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: ${SCROLL_HOVER}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QSlider::groove:horizontal { height: 4px; background: rgba(255, 255, 255, 30); border-radius: 2px; }
QSlider::sub-page:horizontal { background: ${ACCENT}; border-radius: 2px; }
QSlider::handle:horizontal {
    background: white; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}
"""


def build_stylesheet() -> str:
    """Fill the placeholders in the QSS template and return the final stylesheet."""
    tokens = {
        "TEXT": Colors.TEXT,
        "TEXT_DIM": Colors.TEXT_DIM,
        "ACCENT": Colors.ACCENT,
        "ACCENT_LIGHT": Colors.ACCENT_LIGHT,
        "ACCENT_DEEP": Colors.ACCENT_DEEP,
        "HOVER": qss_rgba("#ffffff", 0.06),
        "SELECTED": qss_rgba(Colors.ACCENT, 0.22),
        "SELECTED_BORDER": qss_rgba(Colors.ACCENT_LIGHT, 0.45),
        "ASSIST_BG": qss_rgba("#ffffff", 0.07),
        "ASSIST_BORDER": qss_rgba(Colors.ACCENT_LIGHT, 0.28),
        "TIME_DIM": qss_rgba(Colors.TEXT, 0.45),
        "DIVIDER": qss_rgba("#ffffff", 0.08),
        "SCROLL": qss_rgba(Colors.ACCENT_LIGHT, 0.28),
        "SCROLL_HOVER": qss_rgba(Colors.ACCENT_LIGHT, 0.5),
    }
    return Template(_QSS).substitute(tokens)