"""
Main window implementation for the Floowandereeze & Modding application.
This module provides the main application window that hosts all the different
pages and handles navigation between them.
"""

import pathlib
from typing import List, Type

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QSplashScreen
from pyqttoast import ToastPreset

from pages.background import Background
from pages.card import Card
from pages.config import Config
from pages.face import Face
from pages.field import Field
from pages.icon import Icon
from pages.sleeve import Sleeve
from pages.ui.main_window import Ui_MainWindow
from pages.wallpaper import Wallpaper
from util.python_utils import is_valid_game_path
from util.constants import APP_CONFIG, BG_TEMPLATE
from util.ui_util import show_toast


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    """
    Main window class that serves as the container for all application pages.

    This class handles:
    - Loading and managing different pages (Config, Sleeve, Card, etc.)
    - Navigation between pages through the toolbar
    - Background image management
    - Game path validation and error handling

    Attributes:
        splash: The splash screen widget used during application startup
    """

    def __init__(self, splash: QSplashScreen):
        """
        Initialize the main window.

        Args:
            splash: The splash screen widget to show loading progress
        """
        super().__init__()
        self.splash = splash
        self.setupUi(self)

        self._load_pages()
        self._connect_menu_callbacks()
        self._load_bg()

        self.show()

    def _load_pages(self) -> None:
        """Loads the pages into the main stack based on the validity of the game path."""
        is_valid, error_message = is_valid_game_path(APP_CONFIG.game_path or "")

        if APP_CONFIG.game_path and is_valid:
            pages: List[Type[QtWidgets.QWidget]] = [
                Config,
                Sleeve,
                Card,
                Face,
                Background,
                Icon,
                Field,
                Wallpaper,
            ]

            for page in pages:
                self.splash.showMessage(
                    f"Loading {page.__name__}s...",
                    alignment=QtCore.Qt.AlignBottom | QtCore.Qt.AlignCenter,
                    color=QtCore.Qt.white,
                )
                self.mainStack.addWidget(page())
        else:
            if error_message and APP_CONFIG.game_path:
                show_toast(
                    self,
                    "Game Path",
                    f"There was a problem with the Game Path: {error_message}",
                    ToastPreset.WARNING_DARK,
                )
            self.mainStack.addWidget(Config())
            self.toolBar.setEnabled(False)

    def _connect_menu_callbacks(self) -> None:
        """Connects the menu buttons to their respective pages in the stack."""
        buttons = [
            self.actionconfig_button,
            self.actionsleeve_button,
            self.actioncard_button,
            self.actionface_button,
            self.actionbackground_button,
            self.actionicon_button,
            self.actionfield_button,
            self.actionwallpaper_button,
        ]

        for index, button in enumerate(buttons):
            button.triggered.connect(
                lambda _, idx=index: self.mainStack.setCurrentIndex(idx)
            )

    def _load_bg(self) -> None:
        """Loads the background image based on the configuration."""
        bg_path = (
            pathlib.Path(APP_CONFIG.background_path)
            if APP_CONFIG.background_path
            else None
        )
        if bg_path and bg_path.exists():
            self.setStyleSheet(
                BG_TEMPLATE.replace(
                    "$BG$", f"border-image: url('{APP_CONFIG.background_path}');"
                )
            )
        else:
            self.setStyleSheet(
                f"{BG_TEMPLATE.replace('$BG$', 'border-image: url(:/ui/images/bg.png);')}"
            )
