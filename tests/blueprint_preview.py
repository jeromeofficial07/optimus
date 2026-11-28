"""
Preview the blueprint theme (no AI, voice or database needed).
Run from the project root:   python -m tests.blueprint_preview
"""
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui.blueprint_theme import apply_blueprint_theme
from app.ui.glass_panel import BackgroundWidget, GlassPanel
from app.ui.theme import build_stylesheet

STATES = ["idle", "listening", "thinking", "speaking"]


def main():
    app = QApplication(sys.argv)
    family, extra = apply_blueprint_theme()
    app.setFont(QFont(family, 10))
    app.setStyleSheet(build_stylesheet() + extra)

    from app.ui.blueprint_head import BlueprintVisualizer
    from app.ui.preloader import PreloaderOverlay

    window = BackgroundWidget()
    window.setWindowTitle("OPTIMUS blueprint theme preview")
    window.resize(1150, 660)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(16)

    head_panel = GlassPanel(radius=26, tint=0.45)
    head_layout = QVBoxLayout(head_panel)
    visualizer = BlueprintVisualizer()
    head_layout.addWidget(visualizer)
    layout.addWidget(head_panel, 3)

    chat_panel = GlassPanel(radius=26, tint=0.5)
    chat_layout = QVBoxLayout(chat_panel)
    chat_layout.setContentsMargins(20, 18, 20, 18)
    chat_layout.addWidget(QLabel("Move the mouse around: the eyes and details follow the cursor. Hover a button."))
    row = QHBoxLayout()
    for name in STATES:
        button = QPushButton(name.upper())
        button.setObjectName("PrimaryButton")
        button.clicked.connect(lambda _=False, n=name: visualizer.set_state(n))
        row.addWidget(button)
    replay = QPushButton("REPLAY INTRO")
    replay.setObjectName("PrimaryButton")

    def play():
        visualizer._boot = -1.0
        PreloaderOverlay(window, family).start()

    replay.clicked.connect(play)
    row.addWidget(replay)
    chat_layout.addLayout(row)
    layout.addWidget(chat_panel, 1)

    window.show()
    PreloaderOverlay(window, family).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()