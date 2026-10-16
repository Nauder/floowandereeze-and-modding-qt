"""
Database models for the application.
This module defines all SQLAlchemy models used to store application data,
including configuration, card data, and various UI assets.
"""

from typing import ClassVar

from PySide6.QtGui import QIcon
from sqlalchemy import String, Integer, Boolean, LargeBinary, Text, UniqueConstraint
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
    - Background display mode
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mipmap_count: Mapped[int] = mapped_column(Integer, default=10)
    game_path: Mapped[str] = mapped_column(String(610), nullable=True)
    background_path: Mapped[str] = mapped_column(String(610), nullable=True)
    version: Mapped[str] = mapped_column(String(100), nullable=True)
    crypto_key: Mapped[str] = mapped_column(String(100), nullable=True)
    packer: Mapped[str] = mapped_column(String(5), default="LZ4")
    create_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    background_mode: Mapped[str] = mapped_column(String(10), default="stretched")
    asset_region: Mapped[str] = mapped_column(String(3), default="tcg")
    metadata_repository: Mapped[str] = mapped_column(
        String(150), default="Nauder/floowandereeze-and-modding-etl"
    )
    metadata_branch: Mapped[str] = mapped_column(String(255), default="")
    metadata_last_source: Mapped[str] = mapped_column(Text, nullable=True)


class SleeveModel(UnityAsset, base):
    """
    Model for card sleeve assets.

    Stores information about card sleeves including:
    - bundle: Unique identifier for the sleeve asset
    - thumb: Thumbnail icon for the sleeve
    """

    __tablename__ = "sleeve"

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class SleeveOcgModel(UnityAsset, base):
    """OCG counterpart to :class:`SleeveModel`."""

    __tablename__ = "sleeve_ocg"

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

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


class CardOcgModel(UnityAsset, base):
    """OCG counterpart to :class:`CardModel`."""

    __tablename__ = "card_ocg"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))
    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    modded_name: Mapped[str] = mapped_column(String(255), nullable=True)
    modded_description: Mapped[str] = mapped_column(String(255), nullable=True)
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

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

    name: Mapped[str] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
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

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

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

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

    name: Mapped[str] = mapped_column(String(255), unique=True)
    small: Mapped[str] = mapped_column(String(255), unique=True)
    medium: Mapped[str] = mapped_column(String(255), unique=True)
    o_medium: Mapped[str] = mapped_column(String(255), unique=True)
    r_medium: Mapped[str] = mapped_column(String(255), unique=True)
    large: Mapped[str] = mapped_column(String(255), unique=True)
    o_large: Mapped[str] = mapped_column(String(255), unique=True)
    r_large: Mapped[str] = mapped_column(String(255), unique=True)
    thumb: QIcon = QIcon()


class CoinModel(UnityAsset, base):
    """
    Model for coin assets.

    Coins use the same three-resolution bundle layout as player icons.
    """

    __tablename__ = "coin"

    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

    name: Mapped[str] = mapped_column(String(255), unique=True)
    bundle_small: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_medium: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_big: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class SummonAnimationAssetModel(base):
    """One remote container component; object IDs remain decimal text."""

    __tablename__ = "summon_animation_asset"
    __table_args__ = (
        UniqueConstraint(
            "game_region", "source", "bundle", "asset_path", name="uq_summon_component"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_region: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    bundle: Mapped[str] = mapped_column(Text, nullable=False)
    asset_path: Mapped[str] = mapped_column(Text, nullable=False)
    card_id: Mapped[str] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=True)
    asset_region: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=True)
    scale: Mapped[str] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=True)
    path_id: Mapped[str] = mapped_column(Text, nullable=True)
    serialized_file: Mapped[str] = mapped_column(Text, nullable=True)
    asset_name: Mapped[str] = mapped_column(Text, nullable=True)
    spine_version: Mapped[str] = mapped_column(Text, nullable=True)
    animation_names: Mapped[str] = mapped_column(Text, nullable=True)
    atlas_pages: Mapped[str] = mapped_column(Text, nullable=True)
    external_references: Mapped[str] = mapped_column(Text, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=True)
    height: Mapped[int] = mapped_column(Integer, nullable=True)


class SummonAnimationEditModel(base):
    """Local state for a physical bundle, independent of metadata refresh."""

    __tablename__ = "summon_animation_edit"
    __table_args__ = (
        UniqueConstraint("installation", "relative_path", name="uq_summon_edit"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    installation: Mapped[str] = mapped_column(Text)
    relative_path: Mapped[str] = mapped_column(Text)
    manifest: Mapped[str] = mapped_column(Text)
    modified: Mapped[bool] = mapped_column(Boolean, default=False)


base.metadata.create_all(engine)
