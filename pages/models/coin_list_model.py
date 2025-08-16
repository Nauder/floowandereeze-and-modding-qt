import re
from io import BytesIO
from os.path import join
from threading import Thread

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from UnityPy import load as unity_load
from typing_extensions import override

from database.models import CoinModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from services.coin_service import CoinService
from util.constants import APP_CONFIG


class CoinListModel(AssetListModel):
    """
    List model for coin interface metadata.

    This model manages the display of coin-related interface elements
    and provides thumbnails for the coin assets.
    """

    def __init__(self, coins=None):
        super().__init__(coins or [], CoinModel)
        self.coin_service = CoinService()  # Add service instance
        self.refresh()

    @override
    def refresh(self):
        """Refresh the list of coin assets from the database."""
        self.assets = session.query(CoinModel).all()

        # Load thumbnails in separate threads
        refresh_threads = [
            Thread(target=lambda coin=coin_asset: self.refresh_coin(coin))
            for coin_asset in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_coin(self, coin):
        """Load thumbnail for a coin asset."""
        try:
            coin.thumb = self._create_coin_thumbnail(coin)
        except Exception as e:
            print(f"Error creating coin thumbnail for {coin.bundle}: {e}")
            coin.thumb = QIcon(":/ui/images/icon.png")  # Fallback icon

    def _create_coin_thumbnail(self, coin: CoinModel) -> QIcon:
        """Create a thumbnail icon from the coin's head region."""
        try:
            bundle_path = join(
                APP_CONFIG.game_path,
                "0000",
                coin.bundle[:2],
                coin.bundle,
            )

            # Load the Unity bundle
            env = unity_load(bundle_path)

            # Find and extract the coin texture
            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    data = obj.read()

                    # Look for the coin texture
                    if re.search(re.compile(r"coin\d\dtex"), data.m_Name.lower()) or (
                        "cointoss" in data.m_Name.lower()
                        and "icon" not in data.m_Name.lower()
                    ):
                        coin_img = data.image.convert("RGBA")

                        # Get head region for thumbnail using the service method
                        head_region, _ = self.coin_service.get_coin_regions(
                            coin_img.size
                        )

                        # Extract head region
                        head_img = coin_img.crop(
                            (
                                head_region[0],
                                head_region[1],
                                head_region[0] + head_region[2],
                                head_region[1] + head_region[3],
                            )
                        )

                        # Create circular thumbnail
                        thumbnail_size = (128, 128)  # Keep original size
                        head_img = head_img.resize(
                            thumbnail_size, Image.Resampling.LANCZOS
                        )

                        # Create circular mask
                        mask = Image.new("L", thumbnail_size, 0)
                        draw = ImageDraw.Draw(mask)
                        draw.ellipse(
                            (0, 0, thumbnail_size[0], thumbnail_size[1]), fill=255
                        )

                        # Apply circular mask
                        circular_img = Image.new("RGBA", thumbnail_size, (0, 0, 0, 0))
                        circular_img.paste(head_img, (0, 0))
                        circular_img.putalpha(mask)

                        # Convert to QIcon
                        img_bytes = BytesIO()
                        circular_img.save(img_bytes, format="PNG")
                        img_bytes.seek(0)
                        pixmap = QPixmap()
                        pixmap.loadFromData(img_bytes.getvalue())

                        return QIcon(pixmap)

        except Exception as e:
            print(f"Error creating coin thumbnail for {coin.bundle}: {e}")

        return QIcon(":/ui/images/icon.png")  # Fallback icon

    def data(self, index, role):
        """Provide data for the list view."""
        if role == Qt.DisplayRole:
            asset = self.assets[index.row()]
            return asset.bundle

        if role == Qt.DecorationRole:
            return (
                self.assets[index.row()].thumb
                if hasattr(self.assets[index.row()], "thumb")
                else QIcon()
            )

    def set_backup_state(self, asset_id, has_backup: bool):
        """Set backup state for an asset (not applicable for CoinModel)."""
        pass

    def reset_backups(self):
        """Reset backup states (not applicable for CoinModel)."""
        pass
