"""Offscreen frame import, stale preview, playback and worker lifetime checks."""

import time
from unittest.mock import Mock, patch
import unittest

from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest

from test_summon_animation_ui import page_module
import test_summon_frames as fixtures
from widgets.summon_frames_editor import SummonFramesEditor
from test_summon_animations import row
from unity.summon_frames import FrameOptions, ImportMemoryWarning


class FramesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.service = Mock()
        self.dialog = SummonFramesEditor(self.service, [row()])
        self.addCleanup(self.dispose)

    def dispose(self):
        self.dialog.close()
        self.dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )

    def plan(self):
        return {
            "preview": [
                fixtures.png(color=(255, 0, 0, 255)),
                fixtures.png(color=(0, 255, 0, 255)),
            ],
            "indices": [0, 1, 0, 1],
            "times": [0, 0.25, 0.5, 0.75],
            "duration": 1,
            "source_duration": 2,
            "options": FrameOptions(),
            "summary": "4 playback frames · synthetic target",
            "affected": [],
        }

    def wait_worker(self):
        deadline = time.monotonic() + 5
        while self.dialog.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(self.dialog.worker)

    def test_mp4_picker_prepares_preview(self):
        self.service.prepare_frame_animation.return_value = self.plan()
        with patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=("animation.mp4", "MP4 files (*.mp4)"),
        ) as picker:
            self.dialog.gif_button.click()
        self.assertIn("*.mp4", picker.call_args.args[3])
        self.app.processEvents()
        self.wait_worker()
        self.assertEqual(self.dialog.source.text(), "animation.mp4")
        self.assertTrue(self.dialog.apply.isEnabled())
        self.assertEqual(
            self.service.prepare_frame_animation.call_args.args[1], "animation.mp4"
        )

    def test_large_import_cancelled_before_conversion(self):
        self.service.prepare_frame_animation.side_effect = ImportMemoryWarning(
            "Estimated working memory: 900 MiB. Continue importing?"
        )
        self.dialog.prepared(self.plan())
        self.dialog.source.setText("large.mp4")
        with patch.object(
            QtWidgets.QMessageBox,
            "warning",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as warning:
            self.dialog.prepare()
            self.wait_worker()
        warning.assert_called_once()
        self.assertEqual(self.service.prepare_frame_animation.call_count, 1)
        self.assertIsNone(self.dialog.plan)
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertTrue(self.dialog.generate.isEnabled())
        self.assertIn("cancelled", self.dialog.status.text())

    def test_large_import_approval_retries_with_same_input_and_locks(self):
        self.service.prepare_frame_animation.side_effect = [
            ImportMemoryWarning("Estimated working memory: 900 MiB."),
            self.plan(),
        ]
        self.dialog.source.setText("large.mp4")
        self.dialog.lower_quality = True

        def approve(*args):
            self.assertIsNotNone(self.dialog.worker)
            self.assertFalse(self.dialog.generate.isEnabled())
            self.assertFalse(self.dialog.source.isEnabled())
            self.dialog.prepare()  # Reentrant requests cannot start another worker.
            return QtWidgets.QMessageBox.StandardButton.Yes

        with patch.object(QtWidgets.QMessageBox, "warning", side_effect=approve):
            self.dialog.prepare()
            self.wait_worker()
        calls = self.service.prepare_frame_animation.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args, calls[1].args)
        self.assertEqual(
            calls[1].kwargs, {"lower_quality": True, "allow_large_import": True}
        )
        self.assertTrue(self.dialog.apply.isEnabled())

    def test_memory_approval_does_not_bypass_atlas_errors(self):
        self.service.prepare_frame_animation.side_effect = [
            ImportMemoryWarning("Estimated working memory: 900 MiB."),
            ValueError("Too many frames for available atlas cells."),
        ]
        self.dialog.source.setText("large.mp4")
        with patch.object(
            QtWidgets.QMessageBox,
            "warning",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.dialog.prepare()
            self.wait_worker()
        self.assertIn("atlas cells", self.dialog.status.text())
        self.assertIsNone(self.dialog.plan)
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertTrue(self.dialog.generate.isEnabled())

    def test_prepare_play_scrub_and_settings_invalidate_apply(self):
        self.service.prepare_frame_animation.return_value = self.plan()
        self.dialog.source.setText("synthetic.gif")
        self.dialog.prepare()
        self.assertFalse(self.dialog.generate.isEnabled())
        self.wait_worker()
        self.assertTrue(self.dialog.apply.isEnabled())
        self.dialog.slider.setValue(2)
        self.assertEqual(self.dialog.time_label.text(), "0.500 s")
        self.dialog.toggle_play()
        self.assertTrue(self.dialog.timer.isActive())
        self.dialog.controls["fps"].setValue(20)
        self.assertFalse(self.dialog.timer.isActive())
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertIsNone(self.dialog.plan)

    def test_failure_recovers_controls_and_close_is_guarded(self):
        def slow_fail(*_, **_kwargs):
            time.sleep(0.05)
            raise ValueError("unsupported pointer")

        self.service.prepare_frame_animation.side_effect = slow_fail
        self.dialog.source.setText("synthetic.gif")
        self.dialog.prepare()
        self.dialog.close()
        self.assertIsNotNone(self.dialog.worker)
        self.wait_worker()
        self.assertIn("unsupported pointer", self.dialog.status.text())
        self.assertTrue(self.dialog.generate.isEnabled())
        self.assertFalse(self.dialog.apply.isEnabled())

    def test_apply_exact_preview_and_disable_after_success(self):
        plan = self.plan()
        self.dialog.prepared(plan)
        self.dialog.set_controls(True)
        result = {"manifests": [], "modified": True, "affected": []}
        self.service.apply_frame_animation.return_value = result
        received = []
        self.dialog.applied.connect(received.append)
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.dialog.apply_plan()
        self.wait_worker()
        self.assertEqual(received, [result])
        self.service.apply_frame_animation.assert_called_once_with(plan)
        self.assertFalse(self.dialog.apply.isEnabled())
        self.assertIsNone(self.dialog.plan)

    def test_picked_input_auto_prepares_with_selected_quality_and_hidden_settings(self):
        self.service.prepare_frame_animation.return_value = self.plan()
        dialog = SummonFramesEditor(
            self.service,
            [row()],
            source="synthetic.gif",
            lower_quality=True,
            card_name="Synthetic card",
        )
        self.assertTrue(dialog.settings_box.isHidden())
        self.assertEqual(dialog.card_name, "Synthetic card")
        deadline = time.monotonic() + 5
        while dialog.plan is None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        while dialog.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNotNone(dialog.plan)
        self.assertTrue(
            self.service.prepare_frame_animation.call_args.kwargs["lower_quality"]
        )
        dialog.close()
        dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )

    def test_shared_quality_warning_visible_in_preview_and_confirmation(self):
        plan = self.plan()
        plan.update(
            quality_label="Shared quality",
            quality_warning="Replacing it affects both quality modes.",
        )
        self.dialog.prepared(plan)
        self.dialog.set_controls(True)
        self.assertIn("both quality modes", self.dialog.notice.text())
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ) as question:
            self.dialog.apply_plan()
        self.assertIn("both quality modes", question.call_args.args[2])
        self.service.apply_frame_animation.assert_not_called()

    def test_source_change_invalidates_prepared_plan(self):
        self.dialog.prepared(self.plan())
        self.dialog.set_controls(True)
        self.dialog.source.setText("another.gif")
        self.assertIsNone(self.dialog.plan)
        self.assertFalse(self.dialog.slider.isEnabled())


if __name__ == "__main__":
    unittest.main()
