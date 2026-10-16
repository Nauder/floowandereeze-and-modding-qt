from typing_extensions import override


from database.models import IconModel
from threading import Thread

from pages.models.named_asset_list_model import NamedAssetListModel
from unity.unity_utils import fetch_bundle_thumb


class IconListModel(NamedAssetListModel):

    def __init__(self, icons=None):
        super().__init__(icons or [], IconModel)
        self.show_favorites = False
        self.refresh()

    @override
    def refresh(self):
        self.assets = self.named_query(IconModel).all()

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
