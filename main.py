import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import QSplashScreen

from database.objects import session
from pages.main_window import MainWindow
from util.ui_util import get_dark_mode_palette

if __name__ == "__main__":

    app = QtWidgets.QApplication(sys.argv)
    app.setPalette(get_dark_mode_palette(app))

    try:
        splash_pixmap = QPixmap(":/ui/images/bg.png")
        splash = QSplashScreen(splash_pixmap)
        splash.setFont(QFont("Segoe UI", 14))
        splash.showMessage("Starting...", 4, "#FFFFFF")
        splash.show()

        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding")

        window.show()

        splash.finish(window)

        app.exec()

        session.commit()
    except Exception as error:
        # QtWidgets.QMessageBox.critical(None, 'Error', str(error))
        session.rollback()
        raise error
    finally:
        session.close()
