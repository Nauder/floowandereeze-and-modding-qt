"""
Database models for the application.
This module defines all SQLAlchemy models used to store application data,
including configuration, card data, and various UI assets.
"""

from typing import ClassVar

from PySide6.QtGui import QIcon
from sqlalchemy import String, Integer, Boolean, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.objects import base, engine


# In theory all that inherit from this should have a `thumb: QIcon = QIcon()` attribute, but
# pyinstaller fails to detect the attribute, so it is explicitly declared in the children.
class UnityAsset:
    """
    Base class for Unity asset models.

    This class provides common fields for all Unity asset models:
    - id: Unique identifier
    - favorite: Whether the asset is marked as favorite
    - has_backup: Whether the asset has a backup

    Note: All child classes should have a `thumb: QIcon = QIcon()` attribute,
    but it's explicitly declared in children due to PyInstaller limitations.
    """

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    has_backup: Mapped[bool] = mapped_column(Boolean, default=False)


class AppConfig(base):
    """
    Application configuration model.

    Stores global application settings including:
    - Game path and background path
    - Version and crypto key
    - Mipmap settings and backup preferences
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mipmap_count: Mapped[int] = mapped_column(Integer, default=10)
    game_path: Mapped[str] = mapped_column(String(610))
    background_path: Mapped[str] = mapped_column(String(610), nullable=True)
    version: Mapped[str] = mapped_column(String(100), nullable=True)
    crypto_key: Mapped[str] = mapped_column(String(100), nullable=True)
    packer: Mapped[str] = mapped_column(String(5), default="LZ4")
    create_backup: Mapped[bool] = mapped_column(Boolean, default=False)


class SleeveModel(UnityAsset, base):
    """
    Model for card sleeve assets.

    Stores information about card sleeves including:
    - bundle: Unique identifier for the sleeve asset
    - thumb: Thumbnail icon for the sleeve
    """

    __tablename__ = "sleeve"

    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class CardModel(UnityAsset, base):
    """
    Model for card assets.

    Stores information about cards including:
    - name and description (original and modded)
    - bundle identifier
    - data index for Unity file
    - thumbnail icon
    """

    __tablename__ = "card"

    # Original card name and description are kept separate from metadata so restoration is possible
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))
    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    modded_name: Mapped[bool] = mapped_column(String(255), nullable=True)
    modded_description: Mapped[bool] = mapped_column(String(255), nullable=True)
    data_index: Mapped[int] = mapped_column(Integer)
    unity_file: ClassVar[bool] = False
    thumb: QIcon = QIcon()


class CardMetadataModel(base):
    """
    Model for card metadata.

    Stores additional card data including:
    - name and bundle identifier
    - raw data and decoded data
    - JSON representation of the data
    """

    __tablename__ = "card_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    data_decoded: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=True)


class CardIconModel(UnityAsset, base):
    """
    Model for card icon assets.

    Stores information about card icons including:
    - name and dimensions
    - atlas position coordinates
    - thumbnail icon
    """

    __tablename__ = "card_icon"

    name: Mapped[str] = mapped_column(String(255))
    width: ClassVar[int]
    height: ClassVar[int]
    atlas_x: ClassVar[int]
    atlas_y: ClassVar[int]
    thumb: QIcon = QIcon()


class IconModel(UnityAsset, base):
    """
    Model for player icon assets.

    Stores information about icons including:
    - name
    - bundle identifiers for different sizes
    - thumbnail icon
    """

    __tablename__ = "icon"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    bundle_small: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_medium: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_big: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class WallpaperModel(UnityAsset, base):
    """
    Model for wallpaper assets.

    Stores information about wallpapers including:
    - name
    - bundle identifiers for different components (icon, foreground, background)
    - thumbnail icon
    """

    __tablename__ = "home_art"

    name: Mapped[str] = mapped_column(String(255))
    bundle_icon: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_foreground: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_background: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class FieldModel(UnityAsset, base):
    """
    Model for field assets.

    Stores information about field assets including:
    - bundle identifier
    - position flags (bottom, flipped)
    - thumbnail icon
    """

    __tablename__ = "field"

    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    bottom: Mapped[bool] = mapped_column(Boolean, default=False)
    flipped: Mapped[bool] = mapped_column(Boolean, default=False)
    thumb: QIcon = QIcon()


class FaceModel(UnityAsset, base):
    """
    Model for card face assets.

    Stores information about face assets including:
    - name and unique key
    - thumbnail icon
    """

    __tablename__ = "face"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    key: Mapped[int] = mapped_column(Integer, unique=True)
    thumb: QIcon = QIcon()


class DeckBoxModel(UnityAsset, base):
    """
    Model for deck box assets.

    Stores information about deck boxes including:
    - name
    - bundle identifiers for different sizes and orientations
    - thumbnail icon
    """

    __tablename__ = "deck_box"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    small: Mapped[str] = mapped_column(String(255), unique=True)
    medium: Mapped[str] = mapped_column(String(255), unique=True)
    o_medium: Mapped[str] = mapped_column(String(255), unique=True)
    r_medium: Mapped[str] = mapped_column(String(255), unique=True)
    large: Mapped[str] = mapped_column(String(255), unique=True)
    o_large: Mapped[str] = mapped_column(String(255), unique=True)
    r_large: Mapped[str] = mapped_column(String(255), unique=True)
    thumb: QIcon = QIcon()


base.metadata.create_all(engine)
