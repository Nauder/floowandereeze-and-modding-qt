"""
Constants and configuration used throughout the application.
This module centralizes all application constants, configuration values,
and global state to facilitate updates and maintain consistency.
"""

from database.models import AppConfig
from database.objects import session

# File-related constants
FILE: dict[str, str | list[str]] = {
    "IMAGE_NAME": "image.png",
    "UNITY": "data.unity3d",
    "BACKGROUND": "ShopBGBase02",
    "CARD_SPRITE_ATLAS": "sactx-0-1024x512-BC7-CardSpriteAtlas-57d48bc7",
}

# CSS template for background styling
BG_TEMPLATE: str = """
    #centralwidget {
        $BG$
        margin: 0;
        padding: 0;
    }
    
    .QListView, .QLineEdit {
        background-color: rgba(12, 12, 12, 0.7);
    }
    
    .QPushButton {
        border: 1px solid #121212;
        border-radius: 5px;
        padding: 3px;
        width: 90%;
    }
    
    .QToolBar::item:hover {
        background-color: rgba(12, 12, 12, 0.7);
    }
    
    .QPushButton:hover {
        border: 1px solid darkgreen;
    }
    
    .QPushButton:disabled {
        border: 1px solid #523000;
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
