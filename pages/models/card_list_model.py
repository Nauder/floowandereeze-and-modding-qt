from textwrap import shorten
from threading import Thread

from PySide6.QtGui import Qt
from typing_extensions import override

from database.models import CardModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


class CardListModel(AssetListModel):

    def __init__(self, cards=None):
        super().__init__(cards or [], CardModel)
        self.filter = ""

    @override
    def refresh(self):
        if self.filter != "":
            self.assets = (
                session.query(self.db_model)
                .order_by(self.db_model.name)
                .filter(self.db_model.name.contains(self.filter))
                .all()
            )

            refresh_threads = [
                Thread(target=lambda card=cards_card: self._refresh_card(card))
                for cards_card in self.assets
            ]

            for thread in refresh_threads:
                thread.start()
            for thread in refresh_threads:
                thread.join()

    def _refresh_card(self, card):
        card.thumb = fetch_bundle_thumb(card.bundle, (128, 128))
        if not card.thumb:
            card.thumb = fetch_bundle_thumb(card.bundle, (128, 128), True)
            card.unity_file = True

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return shorten(
                self.assets[index.row()].name,
                width=20,
                placeholder="...",
                replace_whitespace=False,
            )

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
