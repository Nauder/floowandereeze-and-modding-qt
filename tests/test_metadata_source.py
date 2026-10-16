"""Configurable metadata source routing, persistence and refresh regression tests."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtWidgets
from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import objects, migrations

with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
    from services import update_service

_import_engine = create_engine("sqlite:///:memory:")
objects.base.metadata.create_all(_import_engine)
_import_session = sessionmaker(bind=_import_engine)()
with (
    patch.object(objects, "session", _import_session),
    patch.object(migrations, "run_migrations"),
):
    from pages import config as config_page
_import_session.close()
_import_engine.dispose()

from util.metadata_source import (
    DEFAULT_METADATA_REPOSITORY,
    normalize_metadata_source,
    metadata_source_key,
)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        patcher = patch.object(update_service, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_original_default_source_omits_branch_ref(self):
        self.assertEqual(
            update_service._github_source(),
            ("Nauder", "floowandereeze-and-modding-etl", {}),
        )
        config = models.AppConfig()
        self.session.add(config)
        self.session.commit()
        self.assertEqual(config.metadata_repository, DEFAULT_METADATA_REPOSITORY)
        self.assertEqual(config.metadata_branch, "")
        self.assertEqual(
            update_service._github_source(),
            ("Nauder", "floowandereeze-and-modding-etl", {}),
        )

    def test_version_and_parquet_share_saved_repo_and_slash_branch(self):
        self.session.add(
            models.AppConfig(
                metadata_repository="Example/etl",
                metadata_branch="feature/summon-animations",
            )
        )
        self.session.commit()
        response = MagicMock()
        response.json.return_value = {
            "download_url": "https://example.invalid/branch-specific-file"
        }
        response.text = "2026-10-12"
        with patch.object(update_service.requests, "get", return_value=response) as get:
            self.assertEqual(
                update_service.get_github_raw_file("data/version.txt"), "2026-10-12"
            )
            self.assertEqual(
                get.call_args_list[0].args[0],
                "https://api.github.com/repos/Example/etl/contents/data/version.txt",
            )
            self.assertEqual(
                get.call_args_list[0].kwargs["params"],
                {"ref": "feature/summon-animations"},
            )
            self.assertNotIn("params", get.call_args_list[1].kwargs)
        frame = DataFrame({"test": [1]})
        with (
            patch.object(update_service.requests, "get", return_value=response) as get,
            patch.object(update_service, "read_parquet", return_value=frame) as parquet,
        ):
            self.assertIs(
                update_service.get_github_parquet_file(
                    "data/summon_animations.parquet"
                ),
                frame,
            )
            self.assertEqual(
                get.call_args.kwargs["params"], {"ref": "feature/summon-animations"}
            )
            parquet.assert_called_once_with(
                "https://example.invalid/branch-specific-file"
            )

    def test_explicit_overrides_and_blank_branch(self):
        self.session.add(
            models.AppConfig(
                metadata_repository="Example/etl", metadata_branch="feature/test"
            )
        )
        self.session.commit()
        self.assertEqual(
            update_service._github_source("Other", "repo", "release"),
            ("Other", "repo", {"ref": "release"}),
        )
        self.assertEqual(
            update_service._github_source(branch=""), ("Example", "etl", {})
        )

    def test_validation_rejects_invalid_repo_and_whitespace_ref(self):
        self.assertEqual(
            normalize_metadata_source(" Example/etl ", " feature/cutins "),
            ("Example/etl", "feature/cutins"),
        )
        for repo, branch in (
            ("https://github.com/a/b", ""),
            ("a/b/c", ""),
            ("a/..", ""),
            ("a/b", "bad branch"),
        ):
            with self.subTest(repo=repo, branch=branch), self.assertRaises(ValueError):
                normalize_metadata_source(repo, branch)
        self.assertNotEqual(
            metadata_source_key("a/b", "main"),
            metadata_source_key("a/b", "feature/cutins"),
        )

    def test_existing_database_gets_defaults_without_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "old.db")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "CREATE TABLE app_config (id INTEGER PRIMARY KEY, game_path TEXT, version TEXT)"
                )
                connection.execute(
                    "INSERT INTO app_config VALUES (1, 'keep', '2026-10-12')"
                )
                connection.commit()
            migrations.run_migrations(path)
            migrations.run_migrations(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT game_path, version, metadata_repository, metadata_branch, metadata_last_source FROM app_config"
                    ).fetchall(),
                    [("keep", "2026-10-12", DEFAULT_METADATA_REPOSITORY, "", None)],
                )


class SourceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.config = models.AppConfig(asset_region="tcg", version="2026-10-12")
        self.session.add(self.config)
        self.session.commit()
        for name, value in (
            ("session", self.session),
            ("APP_CONFIG", self.config),
            ("show_toast", MagicMock()),
        ):
            patcher = patch.object(config_page, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.page = config_page.Config()
        self.addCleanup(self._close_page, self.page)

    @staticmethod
    def _close_page(page):
        page.close()
        page.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )

    def test_gui_persists_and_restores_default_source(self):
        self.assertEqual(
            self.page.metadataRepositoryLine.text(), DEFAULT_METADATA_REPOSITORY
        )
        self.assertEqual(self.page.metadataBranchLine.text(), "")
        self.page.metadataRepositoryLine.setText("Example/etl")
        self.page.metadataBranchLine.setText("feature/cutins")
        self.page.saveMetadataSourceButton.click()
        self.session.expire_all()
        self.assertEqual(self.config.metadata_repository, "Example/etl")
        self.assertEqual(self.config.metadata_branch, "feature/cutins")
        second = config_page.Config()
        self.addCleanup(self._close_page, second)
        self.assertEqual(second.metadataBranchLine.text(), "feature/cutins")
        self.page.resetMetadataSourceButton.click()
        self.assertEqual(self.config.metadata_repository, DEFAULT_METADATA_REPOSITORY)
        self.assertEqual(self.config.metadata_branch, "")

    def test_invalid_source_never_downloads_or_changes_saved_source(self):
        self.page.metadataRepositoryLine.setText("invalid")
        with patch.object(self.page, "_get_data") as download:
            self.page.updateButton.click()
            download.assert_not_called()
        self.assertEqual(self.config.metadata_repository, DEFAULT_METADATA_REPOSITORY)
        config_page.show_toast.assert_called()

    def test_branch_change_refreshes_same_date_and_records_only_success(self):
        import test_summon_animations as fixtures

        self.session.add(
            models.CardOcgModel(
                name="Known", description="", bundle="00000001", data_index=1
            )
        )
        self.session.add(models.SleeveOcgModel(bundle="00000002"))
        self.session.add(models.SummonAnimationAssetModel(**fixtures.row()))
        self.session.add(models.SleeveModel(bundle="00000003", display_name="Known"))
        self.session.add(
            models.IconModel(
                name="Known",
                bundle_small="00000004",
                bundle_medium="00000005",
                bundle_big="00000006",
                display_name="Known",
            )
        )
        self.session.add(
            models.CardIconModel(
                name="Known", width=1, height=1, x=0, y=0, display_name="Known"
            )
        )
        self.session.add(
            models.CoinModel(
                name="Known",
                bundle_small="00000007",
                bundle_medium="00000008",
                bundle_big="00000009",
                display_name="Known",
            )
        )
        self.session.add(
            models.DeckBoxModel(
                name="Known",
                small="1",
                medium="2",
                o_medium="3",
                r_medium="4",
                large="5",
                o_large="6",
                r_large="7",
                display_name="Known",
            )
        )
        old_source = metadata_source_key(DEFAULT_METADATA_REPOSITORY, "")
        self.config.metadata_last_source = old_source
        self.config.metadata_branch = "feature/cutins"
        self.session.commit()
        calls = []
        names = [
            "update_sleeves",
            "update_cards",
            "update_card_icons",
            "update_faces",
            "update_wallpapers",
            "update_fields",
            "update_icons",
            "update_boxes",
            "update_card_metadata",
            "update_coins",
            "update_summon_animations",
        ]

        class InlineThread:
            def __init__(self, target, args):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

            def join(self):
                pass

        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    config_page, "get_github_raw_file", return_value="2026-10-12"
                )
            )
            stack.enter_context(patch.object(config_page, "Thread", InlineThread))
            for name in names:
                stack.enter_context(
                    patch.object(
                        config_page,
                        name,
                        side_effect=lambda name=name: calls.append(name),
                    )
                )
            self.page._get_data()
            self.assertEqual(calls, names)
            self.assertEqual(
                self.config.metadata_last_source,
                metadata_source_key(DEFAULT_METADATA_REPOSITORY, "feature/cutins"),
            )
            calls.clear()
            self.page._get_data()
            self.assertEqual(calls, [])
            self.config.metadata_branch = "another-branch"
            self.session.commit()
            with patch.object(
                config_page,
                "update_summon_animations",
                side_effect=ValueError("Invalid dataset"),
            ):
                self.page._get_data()
            self.assertNotEqual(
                self.config.metadata_last_source,
                metadata_source_key(DEFAULT_METADATA_REPOSITORY, "another-branch"),
            )


if __name__ == "__main__":
    unittest.main()
