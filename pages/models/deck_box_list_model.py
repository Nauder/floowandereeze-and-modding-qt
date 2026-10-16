"""Database-backed deck box results and favorites."""

from PySide6.QtGui import QIcon

from database.models import DeckBoxModel
from pages.models.named_asset_list_model import NamedAssetListModel
from unity.unity_utils import fetch_bundle_thumb


class DeckBoxListModel(NamedAssetListModel):
    """Show named deck boxes and retain entries with missing bundles."""

    def __init__(self):
        super().__init__([], DeckBoxModel)
        self.show_favorites = False
        self.refresh()

    def refresh(self):
        """Reload rows and notify the result view."""
        query = self.named_query(DeckBoxModel)
        assets = query.all()
        for asset in assets:
            try:
                asset.thumb = fetch_bundle_thumb(asset.large, (96, 96)) or QIcon()
            except (OSError, ValueError):
                asset.thumb = QIcon(":/ui/images/deck_box.png")
        self.beginResetModel()
        self.assets = assets
        self.endResetModel()
