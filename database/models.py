from typing import ClassVar

from PySide6.QtGui import QIcon
from sqlalchemy import String, Integer, Boolean, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.objects import base, engine


# In theory all that inherit from this should have a `thumb: QIcon = QIcon()` attribute, but pyinstaller
# fails to detect the attribute, so it is explicitly declared in the children.
class UnityAsset:
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    has_backup: Mapped[bool] = mapped_column(Boolean, default=False)


class AppConfig(base):
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
    __tablename__ = "sleeve"

    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class CardModel(UnityAsset, base):
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
    __tablename__ = "card_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    data_decoded: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=True)


class CardIconModel(UnityAsset, base):
    __tablename__ = "card_icon"

    name: Mapped[str] = mapped_column(String(255))
    width: ClassVar[int]
    height: ClassVar[int]
    atlas_x: ClassVar[int]
    atlas_y: ClassVar[int]
    thumb: QIcon = QIcon()


class IconModel(UnityAsset, base):
    __tablename__ = "icon"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    bundle_small: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_medium: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_big: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class WallpaperModel(UnityAsset, base):
    __tablename__ = "home_art"

    name: Mapped[str] = mapped_column(String(255))
    bundle_icon: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_foreground: Mapped[str] = mapped_column(String(8), unique=True)
    bundle_background: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class FieldModel(UnityAsset, base):
    __tablename__ = "field"

    bundle: Mapped[str] = mapped_column(String(8), unique=True)
    bottom: Mapped[bool] = mapped_column(Boolean, default=False)
    flipped: Mapped[bool] = mapped_column(Boolean, default=False)
    thumb: QIcon = QIcon()


class FaceModel(UnityAsset, base):
    __tablename__ = "face"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    key: Mapped[int] = mapped_column(Integer, unique=True)
    thumb: QIcon = QIcon()


class DeckBoxModel(UnityAsset, base):
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
