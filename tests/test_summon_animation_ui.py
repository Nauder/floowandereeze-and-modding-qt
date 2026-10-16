"""Offscreen card-first configuration, quality selection and import routing tests."""

import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import objects, migrations
from test_summon_animations import row

_import_engine = create_engine("sqlite:///:memory:")
objects.base.metadata.create_all(_import_engine)
_import_session = sessionmaker(bind=_import_engine)()
with patch.object(objects, "session", _import_session), patch.object(
    migrations, "run_migrations"
):
    from pages import summon_animation as page_module
_import_session.close()
_import_engine.dispose()


class SummonUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.config_value = SimpleNamespace(
            game_path="C:/SyntheticGame/LocalData/player",
            asset_region="tcg",
            packer="LZ4",
        )
        self.config = patch.object(page_module, "APP_CONFIG", self.config_value)
        self.config.start()
        self.addCleanup(self.config.stop)
        with patch.object(page_module.SummonAnimation, "refresh"):
            self.page = page_module.SummonAnimation()
        self.addCleanup(self.dispose_page)

    def dispose_page(self):
        self.page.close()
        self.page.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )

    def wait_worker(self):
        deadline = time.monotonic() + 5
        while self.page._worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(self.page._worker)

    def profiles(self):
        return [
            row("skeleton_json", quality="sd"),
            row("skeleton_json", name="HD.json", quality="highend_hd"),
            row("animation", name="reference", quality=None),
        ]

    def select_card(self):
        self.page._loaded(self.profiles())
        self.page.cardsView.setCurrentIndex(self.page.model.index(0))

    def test_empty_search_and_config_region_filter(self):
        self.page._loaded([])
        self.assertIn("unavailable", self.page.status.text())
        self.page._loaded(
            self.profiles()
            + [
                row(game_region="ocg", asset_region="ocg"),
                row(card_id="99", display_name=None),
            ]
        )
        self.assertEqual(self.page.model.rowCount(), 2)
        self.page.search.setText("123")
        self.assertEqual(self.page.model.rowCount(), 1)
        self.assertEqual(
            self.page.model.data(
                self.page.model.index(0), QtCore.Qt.ItemDataRole.UserRole
            ),
            ("global", "123"),
        )
        self.config_value.asset_region = "ocg"
        self.page._sync_configuration()
        self.assertEqual(self.page.model.rowCount(), 1)
        self.assertEqual(
            self.page.model.data(
                self.page.model.index(0), QtCore.Qt.ItemDataRole.UserRole
            ),
            ("ocg", "123"),
        )

    def test_automatic_region_and_high_quality_default_no_component_controls(self):
        self.select_card()
        self.assertFalse(self.page.lowerQuality.isChecked())
        self.assertTrue(self.page.gifButton.isEnabled())
        self.assertIn("High quality", self.page.qualityHint.text())
        self.assertEqual(
            {r["quality"] for r in self.page.selected_rows}, {"sd", "highend_hd", None}
        )
        for removed in (
            "componentsView",
            "installationRegion",
            "assetRegion",
            "quality",
            "scale",
            "localRoot",
            "streamingRoot",
            "projectButton",
            "importButton",
            "exportButton",
        ):
            self.assertFalse(hasattr(self.page, removed), removed)
        self.page.lowerQuality.setChecked(True)
        self.assertIn("Lower quality", self.page.qualityHint.text())

    def test_config_game_path_and_streaming_root_are_used_without_cross_region_fallback(
        self,
    ):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            streaming = game / "masterduel_Data" / "StreamingAssets" / "AssetBundle"
            streaming.mkdir(parents=True)
            self.config_value.game_path = str(game / "LocalData" / "player")
            self.config_value.asset_region = "ocg"
            service = self.page._service()
            self.assertEqual(service.installation.game_region, "ocg")
            self.assertEqual(
                service.installation.local_root,
                (game / "LocalData" / "player" / "0000").resolve(),
            )
            self.assertEqual(service.installation.streaming_root, streaming.resolve())
        self.config_value.game_path = None
        self.page._sync_configuration()
        self.select_card()
        self.assertFalse(self.page.gifButton.isEnabled())
        with self.assertRaisesRegex(ValueError, "Configuration"):
            self.page._service()

    def test_card_region_common_fallback_does_not_select_other_region(self):
        self.page._loaded(
            [
                row("skeleton_json", asset_region="ocg"),
                row("skeleton_json", name="common.json", asset_region="common"),
            ]
        )
        self.page.cardsView.setCurrentIndex(self.page.model.index(0))
        self.assertEqual(
            {r["asset_region"] for r in self.page.selected_rows}, {"common"}
        )

    def test_quality_unavailable_disables_import(self):
        self.page._loaded([self.profiles()[0]])
        self.page.cardsView.setCurrentIndex(self.page.model.index(0))
        self.assertFalse(self.page.gifButton.isEnabled())
        self.assertIn("unavailable", self.page.qualityHint.text())
        self.page.lowerQuality.setChecked(True)
        self.assertTrue(self.page.gifButton.isEnabled())

    def test_choose_png_automatically_passes_card_source_and_quality(self):
        self.select_card()
        self.page.lowerQuality.setChecked(True)
        with patch.object(
            QtWidgets.QFileDialog,
            "getExistingDirectory",
            return_value="synthetic-frames",
        ), patch.object(self.page.editor, "use_source") as start:
            self.page.editor.choose_pngs()
        start.assert_called_once_with("synthetic-frames")
        with patch.object(self.page.editor, "use_source") as use:
            self.page._import_frames("synthetic-frames")
        use.assert_called_once_with("synthetic-frames")
        self.assertTrue(self.page.editor.lower_quality)
        self.assertEqual(self.page.editor.card_name, "Synthetic card")
        self.assertEqual(self.page.editor.parent(), self.page.editorHost)
        self.assertFalse(isinstance(self.page.editor, QtWidgets.QDialog))

    def preview_plan(self):
        from test_summon_frames_ui import FramesUiTests

        return FramesUiTests().plan()

    def wait_editor(self):
        self.app.processEvents()
        deadline = time.monotonic() + 5
        while self.page.editor.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(self.page.editor.worker)

    def drop(self, urls):
        from PySide6 import QtGui

        mime = QtCore.QMimeData()
        mime.setUrls(urls)
        enter = QtGui.QDragEnterEvent(
            QtCore.QPoint(30, 30),
            QtCore.Qt.DropAction.CopyAction,
            mime,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        self.page.dragEnterEvent(enter)
        event = QtGui.QDropEvent(
            QtCore.QPointF(30, 30),
            QtCore.Qt.DropAction.CopyAction,
            mime,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        self.page.dropEvent(event)
        return enter.isAccepted(), event.isAccepted()

    def test_drop_gif_mp4_and_png_folder_auto_prepares_inline(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import Mock
        from PIL import Image

        self.select_card()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            gif = path / "animation.GIF"
            Image.new("RGBA", (4, 4), "red").save(gif, format="GIF")
            video = path / "animation.MP4"
            # Decode validation runs in the worker, not the drag event handler.
            video.write_bytes(b"video is validated by the preview service")
            frames = path / "PNG frames"
            frames.mkdir()
            Image.new("RGBA", (4, 4), "blue").save(frames / "frame1.PNG")
            service = Mock()
            service.prepare_frame_animation.return_value = self.preview_plan()
            self.page.editor.service = service
            for source in (gif, video, frames):
                with self.subTest(source=source.name):
                    self.assertEqual(
                        self.drop([QtCore.QUrl.fromLocalFile(str(source))]),
                        (True, True),
                    )
                    self.wait_editor()
                    self.assertEqual(self.page.editor.source.text(), str(source))
                    self.assertIsNotNone(self.page.editor.plan)
                    self.assertTrue(self.page.editor.apply.isEnabled())
            self.assertEqual(service.prepare_frame_animation.call_count, 3)

    def test_invalid_empty_remote_and_multiple_drops_keep_current_source(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            png = path / "single.png"
            png.write_bytes(b"unused")
            gif = path / "valid.gif"
            gif.write_bytes(b"unused")
            self.page.editor.source.setText("original.gif")
            for urls in (
                [QtCore.QUrl.fromLocalFile(str(png))],
                [QtCore.QUrl.fromLocalFile(str(gif))],
                [QtCore.QUrl.fromLocalFile(str(path / "missing.gif"))],
                [QtCore.QUrl.fromLocalFile(str(path / "empty"))],
                [QtCore.QUrl("https://example.com/animation.gif")],
                [QtCore.QUrl.fromLocalFile(str(gif))] * 2,
            ):
                self.assertEqual(self.drop(urls), (False, False))
                self.assertEqual(self.page.editor.source.text(), "original.gif")

    def test_source_retained_and_preview_rebuilt_on_card_or_quality_change(self):
        from unittest.mock import Mock

        service = Mock()
        service.prepare_frame_animation.return_value = self.preview_plan()
        with patch.object(self.page, "_service", return_value=service):
            self.page._loaded(
                self.profiles()
                + [
                    dict(r, card_id="456", display_name="Second card")
                    for r in self.profiles()
                ]
            )
            first = next(
                i
                for i in range(self.page.model.rowCount())
                if self.page.model.data(
                    self.page.model.index(i), QtCore.Qt.ItemDataRole.UserRole
                )[1]
                == "123"
            )
            second = 1 - first
            self.page.cardsView.setCurrentIndex(self.page.model.index(first))
            self.page._import_frames("retained.gif")
            self.wait_editor()
            self.page.lowerQuality.setChecked(True)
            self.assertIsNone(self.page.editor.plan)
            self.wait_editor()
            self.assertTrue(
                service.prepare_frame_animation.call_args.kwargs["lower_quality"]
            )
            self.page.cardsView.setCurrentIndex(self.page.model.index(second))
            self.assertIsNone(self.page.editor.plan)
            self.wait_editor()
            self.assertEqual(self.page.editor.source.text(), "retained.gif")
            self.assertEqual(self.page.editor.card_name, "Second card")
            self.assertEqual({r["card_id"] for r in self.page.editor.rows}, {"456"})
            self.assertEqual(service.prepare_frame_animation.call_count, 3)

    def test_worker_locks_target_drop_and_close_until_finished(self):
        from unittest.mock import Mock

        service = Mock()

        def slow_prepare(*_, **__):
            time.sleep(0.1)
            return self.preview_plan()

        service.prepare_frame_animation.side_effect = slow_prepare
        self.select_card()
        self.page.editor.service = service
        self.page._import_frames("retained.gif")
        self.app.processEvents()
        self.assertTrue(self.page.is_busy())
        self.assertFalse(self.page.cardsView.isEnabled())
        self.assertFalse(self.page.lowerQuality.isEnabled())
        from PySide6 import QtGui

        event = QtGui.QCloseEvent()
        self.page.closeEvent(event)
        self.assertFalse(event.isAccepted())
        with patch.object(self.page, "_drop_source", return_value="new.gif"):
            self.assertEqual(
                self.drop([QtCore.QUrl.fromLocalFile("new.gif")]), (False, False)
            )
        self.wait_editor()
        self.assertTrue(self.page.cardsView.isEnabled())
        self.assertTrue(self.page.lowerQuality.isEnabled())
        self.assertFalse(self.page.is_busy())

    def test_drop_before_card_selection_is_retained_for_next_card(self):
        from unittest.mock import Mock

        self.page._import_frames("retained.gif")
        self.wait_editor()
        self.assertEqual(self.page.editor.source.text(), "retained.gif")
        self.assertIsNone(self.page.editor.plan)
        service = Mock()
        service.prepare_frame_animation.return_value = self.preview_plan()
        with patch.object(self.page, "_service", return_value=service):
            self.select_card()
            self.wait_editor()
        self.assertIsNotNone(self.page.editor.plan)

    def test_inline_layout_fits_small_window_with_scrollable_settings(self):
        self.select_card()
        self.page.resize(960, 480)
        self.page.show()
        self.app.processEvents()
        self.assertEqual(self.page.size(), QtCore.QSize(960, 480))
        self.assertLess(self.page.splitter.sizes()[0], self.page.splitter.sizes()[1])
        self.page.editor.settings_toggle.setChecked(True)
        self.app.processEvents()
        self.assertEqual(self.page.size(), QtCore.QSize(960, 480))
        self.assertGreater(self.page.replacementScroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.page.editor.window(), self.page)
        self.assertFalse(self.page.editor.isWindow())
        self.assertTrue(self.page.acceptDrops())
        for child in self.page.findChildren(QtWidgets.QWidget):
            self.assertFalse(child.acceptDrops(), child.objectName())

    def test_worker_failure_is_visible_and_controls_recover(self):
        def fail():
            raise ValueError("Missing dependency")

        self.page._start(fail, lambda _: self.fail("Unexpected success"))
        self.wait_worker()
        self.assertIn("Missing dependency", self.page.status.text())
        self.assertTrue(self.page.isEnabled())

    def test_restore_selects_all_card_backups_without_component_picker(self):
        self.select_card()
        service = SimpleNamespace(restore_component_set=lambda **_: None)
        component = self.profiles()[0]
        entries = [
            {"path": "original-high", "manifest": {"components": [component]}},
            {"path": "original-low", "manifest": {"components": [component]}},
            {
                "path": "another-card",
                "manifest": {"components": [dict(component, card_id="999")]},
            },
        ]
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), patch.object(self.page, "_start") as start:
            self.page._restore_card(service, self.page.selected_rows, entries)
            callback = start.call_args.args[0]
            with patch.object(service, "restore_component_set") as restore:
                callback()
                restore.assert_called_once_with(
                    manifests=["original-high", "original-low"]
                )


if __name__ == "__main__":
    unittest.main()
