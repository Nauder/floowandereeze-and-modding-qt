"""Card Icon List Model Module.

This module provides the list model for card icon assets, handling the display
and management of card icons from the sprite atlas.
"""

from io import BytesIO
import logging
from os.path import join
from threading import Thread

from PIL import Image
from PySide6.QtGui import QIcon, QPixmap
from UnityPy import load as unity_load
from typing_extensions import override

from database.models import CardIconModel
from database.objects import session
from pages.models.named_asset_list_model import NamedAssetListModel
from util.constants import APP_CONFIG, FILE, HIDDEN_ICON_NAME_PARTS

logger = logging.getLogger(__name__)


class CardIconListModel(NamedAssetListModel):
    """
    List model for card icon assets.

    This model manages the display of card icons from the sprite atlas
    and provides thumbnails for each icon.
    """

    def __init__(self, icons=None):
        super().__init__(icons or [], CardIconModel)
        self.atlas_image = None
        self.refresh()

    def _load_atlas_image(self, force_reload=False):
        """Load the card sprite atlas image only once and store in self._atlas_image."""
        if self.atlas_image is not None and not force_reload:
            return  # Already loaded

        try:
            atlas_path = join(
                APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"]
            )
            env = unity_load(atlas_path)

            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    data = obj.read()
                    if FILE["CARD_SPRITE_ATLAS"] in data.m_Name.lower():
                        self.atlas_image = data.image.convert("RGBA")
                        return
        except Exception:
            logger.exception("Error loading the card sprite atlas")
            self.atlas_image = None

    @override
    def refresh(self, force_reload=False):
        """Refresh the list of card icon assets from the database."""
        icons = self.named_query(CardIconModel).all()
        self.assets = [
            icon
            for icon in icons
            if not any(
                hidden_part in icon.name.lower()
                for hidden_part in HIDDEN_ICON_NAME_PARTS
            )
        ]
        self._load_atlas_image(force_reload)  # Ensure atlas is loaded before threads

        # Load thumbnails in separate threads
        refresh_threads = [
            Thread(target=lambda icon=icon_asset: self.refresh_icon(icon))
            for icon_asset in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_icon(self, icon: CardIconModel):
        """Load thumbnail for a card icon asset."""
        try:
            icon.thumb = self._create_icon_thumbnail(icon)
        except Exception:
            logger.exception("Error creating thumbnail for card icon %s", icon.name)
            icon.thumb = QIcon(":/ui/images/icon.png")  # Fallback icon

    def _create_icon_thumbnail(self, icon: CardIconModel) -> QIcon:
        """Create a thumbnail icon from the atlas using cached image."""
        try:
            atlas_img = self.atlas_image
            if atlas_img is None:
                print("Atlas image is not loaded.")
                return QIcon(":/ui/images/icon.png")

            # Extract the icon region using coordinates
            icon_img = atlas_img.crop(
                (icon.x, icon.y, icon.x + icon.width, icon.y + icon.height)
            )

            # Resize for thumbnail
            thumbnail_size = (64, 64)
            icon_img = icon_img.resize(thumbnail_size, Image.Resampling.LANCZOS)

            # Convert to QIcon
            img_bytes = BytesIO()
            icon_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue())

            return QIcon(pixmap)
        except Exception:
            logger.exception("Error creating thumbnail for card icon %s", icon.name)

        return QIcon(":/ui/images/icon.png")  # Fallback icon

    def set_backup_state(self, asset_id: int, has_backup: bool):
        """Set backup state for an asset."""
        for asset in self.assets:
            if asset.id == asset_id:
                asset.has_backup = has_backup
                session.commit()
                break

    def reset_backups(self):
        """Reset backup states for all assets."""
        for asset in self.assets:
            asset.has_backup = False
        session.commit()
