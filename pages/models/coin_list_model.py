from threading import Thread

from typing_extensions import override

from database.models import CoinModel
from pages.models.named_asset_list_model import NamedAssetListModel
from unity.unity_utils import fetch_bundle_thumb


class CoinListModel(NamedAssetListModel):
    """List model for the new size-specific coin assets."""

    def __init__(self, coins=None):
        super().__init__(coins or [], CoinModel)
        self.show_favorites = False
        self.refresh()

    @override
    def refresh(self):
        # Old atlas-based records cannot be edited by the size-based workflow.
        # They remain in the local database until the next metadata refresh.
        query = self.named_query(CoinModel).filter(CoinModel.bundle_small.is_not(None))
        self.assets = query.all()

        refresh_threads = [
            Thread(target=lambda coin=coin_asset: self.refresh_coin(coin))
            for coin_asset in self.assets
        ]
        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def refresh_coin(self, coin: CoinModel):
        coin.thumb = fetch_bundle_thumb(coin.bundle_medium, (140, 140))
