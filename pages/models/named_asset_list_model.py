"""Shared name display and search for accessory assets."""

from textwrap import shorten

from PySide6.QtCore import Qt
from sqlalchemy import func

from database.objects import session
from pages.models.asset_list_model import AssetListModel


def asset_name(asset):
    """Use the datasource name, falling back to the stable asset code."""
    return (
        getattr(asset, "display_name", None)
        or getattr(asset, "name", None)
        or asset.bundle
    )


class NamedAssetListModel(AssetListModel):
    """Apply the card art naming, sorting, and favorites search pattern."""

    def __init__(self, assets, database_model):
        super().__init__(assets, database_model)
        self.filter = ""
        self.show_favorites = False

    @staticmethod
    def name_column(model):
        """Choose the same label expression for search and sorting."""
        code = model.name if hasattr(model, "name") else model.bundle
        return func.coalesce(func.nullif(model.display_name, ""), code)

    def named_query(self, model):
        """Filter by name or show all favorites, as in the card art tab."""
        query = session.query(model)
        if self.show_favorites:
            query = query.filter(model.favorite.is_(True))
        elif self.filter:
            query = query.filter(
                self.name_column(model).contains(self.filter, autoescape=True)
            )
        return query.order_by(self.name_column(model))

    def get_names(self):
        """Supply completion names without loading thumbnails."""
        return [
            name
            for (name,) in session.query(self.name_column(self.db_model))
            .distinct()
            .all()
        ]

    def data(self, index, role):
        """Provide compact labels, full tooltips, and thumbnails."""
        if not index.isValid() or not 0 <= index.row() < len(self.assets):
            return None
        asset = self.assets[index.row()]
        if role == Qt.DisplayRole:
            return shorten(
                asset_name(asset), width=32, placeholder="...", replace_whitespace=False
            )
        if role == Qt.ToolTipRole:
            return asset_name(asset)
        if role == Qt.DecorationRole:
            return asset.thumb
        return None
