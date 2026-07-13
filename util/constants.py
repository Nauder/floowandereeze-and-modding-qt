"""
Constants and configuration used throughout the application.
This module centralizes all application constants, configuration values,
and global state to facilitate updates and maintain consistency.
"""

from database.migrations import run_migrations
from database.models import AppConfig
from database.objects import session

# File related constants
FILE: dict[str, str | list[str]] = {
    "IMAGE_NAME": "image.png",
    "UNITY": "data.unity3d",
    "BACKGROUND": "ShopBGBase02",
    "CARD_SPRITE_ATLAS": "cardspriteatlas",
}

# Coin coordinates related constants
COIN: dict[str, dict[str, list[int]] | list[int]] = {
    "HEAD": {"START": [86, 493], "END": [586, 990]},
    "TAIL": {"START": [407, 34], "END": [904, 530]},
    "REFERENCE_SIZE": [1024, 1024],  # Reference size for the above coordinates
}

# CSS template for background styling
BG_TEMPLATE: str = """
    #centralwidget {
        $BG$
        margin: 0;
        padding: 0;
    }
    
    .QListView, .QLineEdit, .QListWidget, #preview_frame, #current_frame {
        background-color: rgba(12, 12, 12, 0.7);
    }
    
    .QPushButton {
        background-color: #171717;
        color: white;
        border: 1px solid #2f2f2f;
        border-radius: 5px;
        padding: 4px 10px;
        width: 90%;
    }

    .QPushButton[buttonRole="primary"] {
        background-color: #0d6f4f;
        border-color: #15a06f;
        font-weight: 600;
    }

    .QPushButton[buttonRole="warning"] {
        background-color: #5c2d1c;
        border-color: #a65331;
    }

    .QPushButton[buttonRole="neutral"] {
        background-color: #202020;
        border-color: #454545;
    }
    
    .QToolBar::item:hover {
        background-color: rgba(12, 12, 12, 0.7);
    }
    
    .QPushButton:hover {
        border: 1px solid #15a06f;
    }
    
    .QPushButton:disabled {
        border: 1px solid #523000;
        color: #858585;
    }

    QToolBar {
        background-color: rgba(12, 12, 12, 0.82);
        spacing: 0px;
    }

    QToolBar QToolButton {
        color: white;
        min-width: 92px;
        max-width: 92px;
        min-height: 68px;
        max-height: 68px;
        padding: 4px 0px;
        margin: 0px;
        text-align: center;
    }

    QToolBar QToolButton:checked {
        background-color: rgba(13, 111, 79, 0.85);
        border-bottom: 2px solid #15a06f;
    }
"""
"""
    CSS template to apply on background changes, the $VALUE$ placeholders must be replaced with nothing 
    or valid CSS
"""


# File filter for image selection dialogs
IMAGE_FILTER: str = "Image Files (*.png *.jpg *.jpeg)"
"""
    Types of supported images
"""

# URL for data updates
DATA_URL: str = (
    "https://raw.githubusercontent.com/Nauder/floowandereeze-and-modding/main/data.json"
)
"""
    Data update file URL
"""

HIDDEN_ICON_NAME_PARTS: tuple[str, str, str, str] = (
    "link_num",
    "mask",
    "rarity",
    "turncounter",
)
"""
    Icons that most users don't want to edit, so they are hidden by default
"""

# Check for migrations before getting app config data
run_migrations()

# Global application configuration from database
APP_CONFIG: AppConfig = session.query(AppConfig).first()
"""
    Database user config, created if not exists on start.
"""


class AppSession:
    """
    Global application session state.

    This class holds state variables that persist throughout the application's
    lifetime but don't need to be stored in the database.

    Attributes:
        fresh_card_metadata: Flag indicating if card metadata needs to be refreshed
    """

    fresh_card_metadata = False


# Global application session instance
APP_SESSION: AppSession = AppSession()

if not APP_CONFIG:
    new_app = AppConfig()
    session.add(new_app)
    APP_CONFIG = new_app
