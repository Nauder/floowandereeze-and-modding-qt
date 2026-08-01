"""
Main entry point for the Floowandereeze & Modding application.
This module initializes the Qt application, sets up the UI theme,
and handles the main application window and splash screen.
"""

import sys

from util.error_logging import setup_error_logging

# Install crash handling before importing the UI or application modules so that
# startup failures are written to disk as well.
setup_error_logging()

# These imports intentionally follow logger setup so import-time startup crashes
# are captured in the packaged, windowless application.
# pylint: disable=wrong-import-position,wrong-import-order,ungrouped-imports
from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import QSplashScreen

from database.objects import session
from database.migrations import run_migrations
from pages.main_window import MainWindow
from util.ui_util import get_dark_mode_palette
# pylint: enable=wrong-import-position,wrong-import-order,ungrouped-imports

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

        # Run database migrations
        splash.showMessage("Updating database...", 4, "#FFFFFF")
        run_migrations()

        # Create and show main window
        splash.showMessage("Loading interface...", 4, "#FFFFFF")
        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding")
        window.showMaximized()

        # Close splash screen when main window is ready
        splash.finish(window)

        # Start the application event loop
        app.exec()

        # Commit any pending database changes
        session.commit()
    except Exception:
        # Rollback database changes on error
        session.rollback()
        raise
    finally:
        # Always close the database session
        session.close()
