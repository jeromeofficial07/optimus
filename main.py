"""
OPTIMUS entry point.
Applies the chosen interface theme, then launches the assistant.
"""
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.config import APP_NAME, UI_THEME
from app.ui.theme import FONT_FAMILY, build_stylesheet


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    family = FONT_FAMILY
    if UI_THEME == "commander":
        from app.ui.commander_theme import apply_commander_theme
        family = apply_commander_theme()          # Must run before the window is created

    from app.ui.advanced_window import AdvancedMainWindow   # Imported after the theme is applied
    app.setFont(QFont(family, 10))
    app.setStyleSheet(build_stylesheet())

    window = AdvancedMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()