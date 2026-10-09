"""Database-backed deck box results and favorites."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from database.models import DeckBoxModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


class DeckBoxListModel(AssetListModel):
    """Show named deck boxes and retain entries with missing bundles."""

    def __init__(self):
        super().__init__([], DeckBoxModel)
        self.show_favorites = False
        self.refresh()

    def refresh(self):
        """Reload rows and notify the result view."""
        query = session.query(DeckBoxModel)
        if self.show_favorites:
            query = query.filter(DeckBoxModel.favorite.is_(True))
        assets = query.order_by(DeckBoxModel.name).all()
        for asset in assets:
            try:
                asset.thumb = fetch_bundle_thumb(asset.large, (96, 96)) or QIcon()
            except (OSError, ValueError):
                asset.thumb = QIcon(":/ui/images/deck_box.svg")
        self.beginResetModel()
        self.assets = assets
        self.endResetModel()

    def data(self, index, role):
        """Provide the box name and thumbnail for each result."""
        if not index.isValid() or not 0 <= index.row() < len(self.assets):
            return None
        asset = self.assets[index.row()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return asset.name
        if role == Qt.DecorationRole:
            return asset.thumb
        return None
