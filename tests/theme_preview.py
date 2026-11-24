"""
Preview the commander theme (no AI, voice or database needed).
Run from the project root:   python -m tests.theme_preview
"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui.commander_head import CommanderVisualizer
from app.ui.commander_theme import apply_commander_theme
from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.theme import build_stylesheet

STATES = ["idle", "listening", "thinking", "speaking"]


def main():
    app = QApplication(sys.argv)
    family = apply_commander_theme()
    app.setFont(QFont(family, 10))
    app.setStyleSheet(build_stylesheet())

    window = BackgroundWidget()
    window.setWindowTitle("OPTIMUS commander theme preview")
    window.resize(1100, 640)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    head_panel = GlassPanel(radius=26, tint=0.45)
    head_layout = QVBoxLayout(head_panel)
    visualizer = CommanderVisualizer()
    head_layout.addWidget(visualizer)
    layout.addWidget(head_panel, 3)

    chat_panel = GlassPanel(radius=26, tint=0.5)
    chat_layout = QVBoxLayout(chat_panel)
    note = QLabel("Steel panels, hex-grid backdrop and scanlines. Click a state, or let it cycle every 4 seconds.")
    note.setWordWrap(True)
    chat_layout.addWidget(note)
    row = QHBoxLayout()
    for name in STATES:
        button = QPushButton(name.title())
        button.setObjectName("PrimaryButton")
        button.clicked.connect(lambda _=False, n=name: visualizer.set_state(n))
        row.addWidget(button)
    chat_layout.addLayout(row)
    layout.addWidget(chat_panel, 1)

    index = {"i": 0}

    def cycle():
        index["i"] = (index["i"] + 1) % len(STATES)
        visualizer.set_state(STATES[index["i"]])

    timer = QTimer(window)
    timer.timeout.connect(cycle)
    timer.start(4000)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()