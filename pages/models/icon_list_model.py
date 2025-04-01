from typing_extensions import override

from PySide6.QtGui import Qt

from database.models import IconModel
from database.objects import session
from threading import Thread

from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


class IconListModel(AssetListModel):

    def __init__(self, icons=None):
        super().__init__(icons or [], IconModel)
        self.refresh()

    @override
    def refresh(self):
        self.assets = session.query(IconModel).all()

        refresh_threads = [
            Thread(target=lambda icon=icons_icon: self.refresh_icon(icon))
            for icons_icon in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_icon(self, icon: IconModel):
        icon.thumb = fetch_bundle_thumb(icon.bundle_small, (140, 140))

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
