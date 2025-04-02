"""
Main entry point for the Floowandereeze & Modding application.
This module initializes the Qt application, sets up the UI theme,
and handles the main application window and splash screen.
"""

import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import QSplashScreen

from database.objects import session
from pages.main_window import MainWindow
from util.ui_util import get_dark_mode_palette

if __name__ == "__main__":
    # Initialize the Qt application
    app = QtWidgets.QApplication(sys.argv)
    app.setPalette(get_dark_mode_palette(app))

    try:
        # Create and show splash screen
        splash_pixmap = QPixmap(":/ui/images/bg.png")
        splash = QSplashScreen(splash_pixmap)
        splash.setFont(QFont("Segoe UI", 14))
        splash.showMessage("Starting...", 4, "#FFFFFF")
        splash.show()

        # Create and show main window
        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding")
        window.show()

        # Close splash screen when main window is ready
        splash.finish(window)

        # Start the application event loop
        app.exec()

        # Commit any pending database changes
        session.commit()
    except Exception as error:
        # Rollback database changes on error
        session.rollback()
        raise error
    finally:
        # Always close the database session
        session.close()
