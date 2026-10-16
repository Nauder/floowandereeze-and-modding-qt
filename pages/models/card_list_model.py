from textwrap import shorten
from threading import Thread

from PySide6.QtGui import Qt
from typing_extensions import override
from sqlalchemy import or_

from database.models import CardModel, CardOcgModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb
from util.constants import APP_CONFIG


class CardListModel(AssetListModel):

    def __init__(self, cards=None):
        super().__init__(cards or [], CardModel)
        self.filter = ""
        self.show_favorites = False
        self.search_description = False
        self.search_bundle = False

    @override
    def refresh(self):
        self.db_model = CardOcgModel if APP_CONFIG.asset_region == "ocg" else CardModel
        query = session.query(self.db_model)

        if self.filter != "" and not self.show_favorites:
            search_fields = [self.db_model.name.contains(self.filter)]
            if self.search_description:
                search_fields.append(self.db_model.description.contains(self.filter))
            if self.search_bundle:
                search_fields.append(self.db_model.bundle.contains(self.filter))
            query = query.filter(or_(*search_fields))

        if self.show_favorites:
            query = query.filter(self.db_model.favorite == True)

        self.assets = query.order_by(self.db_model.name).all()

        refresh_threads = [
            Thread(target=lambda card=cards_card: self._refresh_card(card))
            for cards_card in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def _refresh_card(self, card):
        card.thumb = fetch_bundle_thumb(card.bundle, (128, 128), preserve_aspect=True)
        if not card.thumb:
            card.thumb = fetch_bundle_thumb(
                card.bundle, (128, 128), True, preserve_aspect=True
            )
            card.unity_file = True

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return shorten(
                self.assets[index.row()].name,
                width=32,
                placeholder="...",
                replace_whitespace=False,
            )

        if role == Qt.ToolTipRole:
            return self.assets[index.row()].name

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
