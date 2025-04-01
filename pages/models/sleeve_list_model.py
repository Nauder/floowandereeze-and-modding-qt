from threading import Thread
from typing_extensions import override

from PySide6.QtGui import Qt

from database.models import SleeveModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


class SleeveListModel(AssetListModel):

    def __init__(self, sleeves=None):
        super().__init__(sleeves or [], SleeveModel)
        self.refresh()

    @override
    def refresh(self):
        self.assets = session.query(SleeveModel).all()

        refresh_threads = [
            Thread(target=lambda sleeve=sleeves_sleeve: self.refresh_sleeve(sleeve))
            for sleeves_sleeve in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_sleeve(self, sleeve):
        sleeve.thumb = fetch_bundle_thumb(sleeve.bundle, (128, 181))

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
