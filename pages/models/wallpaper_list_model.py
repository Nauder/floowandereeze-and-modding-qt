from threading import Thread
from typing_extensions import override

from PySide6.QtGui import Qt

from database.models import WallpaperModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb
from util.python_utils import max_ratio_within_limit


class WallpaperListModel(AssetListModel):

    def __init__(self, wallpapers=None):
        super().__init__(wallpapers or [], WallpaperModel)
        self.refresh()

    @override
    def refresh(self):
        self.assets: list[WallpaperModel] = session.query(WallpaperModel).all()

        refresh_threads = [
            Thread(target=lambda asset=assets_asset: self.refresh_thumb(asset))
            for assets_asset in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_thumb(self, asset: WallpaperModel):
        size = max_ratio_within_limit(
            fetch_bundle_thumb(asset.bundle_foreground, None)
            .availableSizes()[0]
            .toTuple(),
            200,
        )
        asset.thumb = fetch_bundle_thumb(asset.bundle_foreground, (size[1], size[0]))

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return ""

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
