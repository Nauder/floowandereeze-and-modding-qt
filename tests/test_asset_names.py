"""Names, migration, and search regressions using an isolated database."""

import os
from contextlib import closing
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import objects

with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
    from services import update_service

# UI helpers import APP_CONFIG too: isolate that session, not just table creation.
_import_engine = create_engine("sqlite:///:memory:")
objects.base.metadata.create_all(_import_engine)
_import_session = sessionmaker(bind=_import_engine)()
with (
    patch("database.migrations.run_migrations"),
    patch.object(objects, "session", _import_session),
):
    from pages.models import named_asset_list_model as named
    from pages.models import sleeve_list_model as sleeves
_import_session.close()
_import_engine.dispose()

from database.migrations import run_migrations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from widgets import asset_search

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP = QApplication.instance() or QApplication([])


class AssetNameTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        self.app = QApplication.instance() or QApplication([])
        self.engine = create_engine("sqlite:///:memory:")
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.patches = [
            patch.object(module, "session", self.session)
            for module in (named, sleeves, update_service)
        ]
        for patched in self.patches:
            patched.start()

    def tearDown(self):
        for patched in reversed(self.patches):
            patched.stop()
        self.session.close()
        self.engine.dispose()

    def test_refresh_names_preserves_codes_and_local_state(self):
        cases = (
            (models.SleeveModel, "update_sleeves", "bundle", "name"),
            (models.SleeveOcgModel, "update_sleeves", "bundle", "name"),
            (models.IconModel, "update_icons", "name", "display_name"),
            (models.CoinModel, "update_coins", "name", "display_name"),
            (models.DeckBoxModel, "update_boxes", "name", "display_name"),
            (models.CardIconModel, "update_card_icons", "name", "display_name"),
        )
        for model, function, key, remote_column in cases:
            with self.subTest(model=model.__name__):
                columns = {key: key}
                if model in (models.IconModel, models.CoinModel):
                    columns.update(
                        bundle_small="small", bundle_medium="medium", bundle_big="large"
                    )
                elif model is models.DeckBoxModel:
                    columns.update(
                        {
                            field: field
                            for field in (
                                "small",
                                "medium",
                                "large",
                                "o_medium",
                                "r_medium",
                                "o_large",
                                "r_large",
                            )
                        }
                    )
                elif model is models.CardIconModel:
                    columns.update(
                        {field: field for field in ("x", "y", "width", "height")}
                    )
                values = {
                    field: (
                        1
                        if field in ("x", "y", "width", "height")
                        else model.__name__ + field + "_code"
                    )
                    for field in columns
                }
                asset = model(**values, favorite=True, has_backup=True)
                self.session.add(asset)
                self.session.commit()
                original_id = asset.id
                row = {column: values[field] for field, column in columns.items()}
                row[remote_column] = "Blue-Eyes White Dragon"
                with patch.object(
                    update_service,
                    "get_github_parquet_file",
                    return_value=DataFrame([row]),
                ):
                    getattr(update_service, function)()
                self.session.commit()
                self.assertEqual(asset.display_name, "Blue-Eyes White Dragon")
                self.assertEqual(getattr(asset, key), values[key])
                self.assertEqual(asset.id, original_id)
                self.assertTrue(asset.favorite and asset.has_backup)
                # Null translations remain null; older datasets retain known names.
                row[remote_column] = float("nan")
                with patch.object(
                    update_service,
                    "get_github_parquet_file",
                    return_value=DataFrame([row]),
                ):
                    getattr(update_service, function)()
                self.assertIsNone(asset.display_name)
                self.assertEqual(named.asset_name(asset), values[key])

    def test_name_filter_fallback_favorites_and_literal_characters(self):
        assets = [
            models.SleeveModel(
                bundle="aaaa0001", display_name="Blue-Eyes White Dragon"
            ),
            models.SleeveModel(bundle="bbbb0002", favorite=True),
            models.SleeveModel(bundle="cccc0003", display_name="100% Power"),
        ]
        self.session.add_all(assets)
        self.session.commit()
        model = named.NamedAssetListModel(assets, models.SleeveModel)
        model.filter = "white"
        self.assertEqual(model.named_query(models.SleeveModel).all(), [assets[0]])
        model.filter = "%"
        self.assertEqual(model.named_query(models.SleeveModel).all(), [assets[2]])
        model.filter = "bbbb"
        self.assertEqual(model.named_query(models.SleeveModel).all(), [assets[1]])
        model.show_favorites = True
        model.filter = "Dragon"
        self.assertEqual(model.named_query(models.SleeveModel).all(), [assets[1]])
        self.assertIn("Blue-Eyes White Dragon", model.get_names())
        self.assertEqual(
            model.data(model.index(0, 0), Qt.ToolTipRole), assets[0].display_name
        )
        self.assertEqual(model.data(model.index(1, 0), Qt.DisplayRole), "bbbb0002")

    def test_ocg_search_does_not_substitute_a_filtered_tcg_duplicate(self):
        self.session.add_all(
            [
                models.SleeveOcgModel(bundle="same0001", display_name="OCG Dragon"),
                models.SleeveModel(bundle="same0001", display_name="TCG Dragon"),
                models.SleeveModel(bundle="other001", display_name="TCG Magician"),
            ]
        )
        self.session.commit()
        with (
            patch.object(sleeves, "APP_CONFIG", SimpleNamespace(asset_region="ocg")),
            patch.object(sleeves.SleeveListModel, "refresh_sleeve"),
            patch.object(sleeves.Path, "is_file", return_value=True),
            patch.object(sleeves, "prepare_environment", return_value="unused"),
        ):
            model = sleeves.SleeveListModel()
            model.filter = "TCG"
            model.refresh()
            self.assertEqual([asset.bundle for asset in model.assets], ["other001"])

    def test_search_controls_submit_validate_clear_and_ignore_favorites(self):
        page = QWidget()
        page.model = SimpleNamespace(
            show_favorites=False,
            filter="",
            get_names=lambda: ["Blue-Eyes White Dragon"],
        )
        from unittest.mock import MagicMock

        page.model.refresh = MagicMock()
        page.model.layoutChanged = MagicMock()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        layout.addLayout(header)
        with patch.object(asset_search, "show_toast"):
            asset_search.add_asset_search(page, header, layout, "sleeves")
            page.searchEdit.setText("Bl")
            page.searchButton.click()
            page.model.refresh.assert_not_called()
            self.assertIn("3 characters", page.searchHelperLabel.text())
            page.searchEdit.setText("Blue")
            page.searchEdit.returnPressed.emit()
            self.assertEqual(page.model.filter, "Blue")
            page.searchEdit.clear()
            self.assertEqual(page.model.filter, "")
            page.model.refresh.reset_mock()
            page.model.show_favorites = True
            page.searchEdit.setText("Dragon")
            page.searchButton.click()
            page.model.refresh.assert_not_called()
        page.close()

    def test_existing_schema_migration_is_idempotent_and_preserves_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "assets.db")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE app_config (id INTEGER PRIMARY KEY)")
                for table in (
                    "sleeve",
                    "sleeve_ocg",
                    "icon",
                    "card_icon",
                    "coin",
                    "deck_box",
                ):
                    connection.execute(
                        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, favorite BOOLEAN)"
                    )
                    connection.execute(f"INSERT INTO {table} VALUES (1, 1)")
                connection.commit()
            run_migrations(path)
            run_migrations(path)
            with closing(sqlite3.connect(path)) as connection:
                for table in (
                    "sleeve",
                    "sleeve_ocg",
                    "icon",
                    "card_icon",
                    "coin",
                    "deck_box",
                ):
                    self.assertEqual(
                        connection.execute(
                            f"SELECT id, favorite, display_name FROM {table}"
                        ).fetchone(),
                        (1, 1, None),
                    )
