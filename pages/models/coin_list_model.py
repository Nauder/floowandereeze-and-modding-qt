from threading import Thread
from typing_extensions import override

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

from database.models import CoinModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel


class CoinListModel(AssetListModel):
    """
    List model for coin interface metadata.

    This model manages the display of coin-related interface elements
    and provides thumbnails for the coin assets.
    """

    def __init__(self, coins=None):
        super().__init__(coins or [], CoinModel)
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
        # For now, use a default icon since we don't have the actual texture extraction
        # In a full implementation, this would extract the coin texture from the bundle
        try:
            coin.thumb = QIcon(":/ui/images/icon.png")  # Use the app icon as fallback
        except:
            # Fallback for when Qt application is not initialized
            coin.thumb = QIcon()

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
