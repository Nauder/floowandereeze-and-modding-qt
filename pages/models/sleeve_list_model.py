from threading import Thread
from pathlib import Path
from typing_extensions import override

from database.models import SleeveModel, SleeveOcgModel
from database.objects import session
from pages.models.named_asset_list_model import NamedAssetListModel, asset_name
from unity.unity_utils import fetch_bundle_thumb, prepare_environment
from util.constants import APP_CONFIG


class SleeveListModel(NamedAssetListModel):

    def __init__(self, sleeves=None):
        super().__init__(sleeves or [], SleeveModel)
        self.show_favorites = False
        self.refresh()

    @override
    def refresh(self):
        self.db_model = (
            SleeveOcgModel if APP_CONFIG.asset_region == "ocg" else SleeveModel
        )
        self.assets = self._query_sleeves(self.db_model)

        if APP_CONFIG.asset_region == "ocg":
            ocg_bundles = {bundle for (bundle,) in session.query(SleeveOcgModel.bundle)}
            tcg_fallbacks = [
                sleeve
                for sleeve in self._query_sleeves(SleeveModel)
                if sleeve.bundle not in ocg_bundles
                and Path(prepare_environment(False, sleeve.bundle)).is_file()
            ]
            self.assets.extend(tcg_fallbacks)
            self.assets.sort(key=lambda asset: asset_name(asset).casefold())

        refresh_threads = [
            Thread(target=lambda sleeve=sleeves_sleeve: self.refresh_sleeve(sleeve))
            for sleeves_sleeve in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def get_names(self):
        models = (
            (SleeveOcgModel, SleeveModel)
            if APP_CONFIG.asset_region == "ocg"
            else (SleeveModel,)
        )
        return sorted(
            {
                name
                for model in models
                for (name,) in session.query(self.name_column(model)).distinct()
            }
        )

    def refresh_sleeve(self, sleeve):
        sleeve.thumb = fetch_bundle_thumb(sleeve.bundle, (128, 181))

    def _query_sleeves(self, sleeve_model):
        return self.named_query(sleeve_model).all()

    @override
    def reset_backups(self):
        models = (
            (SleeveOcgModel, SleeveModel)
            if APP_CONFIG.asset_region == "ocg"
            else (SleeveModel,)
        )
        for sleeve_model in models:
            session.query(sleeve_model).update({"has_backup": False})
