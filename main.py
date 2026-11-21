"""
OPTIMUS entry point.
Phase 8A: launches the interface with memory and the advanced features.
(To go back to Phase 7, use PersistentMainWindow from app.ui.persistent_window instead.)
"""
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.config import APP_NAME
from app.ui.advanced_window import AdvancedMainWindow
from app.ui.theme import FONT_FAMILY, build_stylesheet


def main():
    """Create the Qt application, apply the theme, show the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont(FONT_FAMILY, 10))       # Default font for every widget
    app.setStyleSheet(build_stylesheet())     # Apply the dark theme everywhere

    window = AdvancedMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()