"""Offscreen Qt checks for backup scope and refresh behavior."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pages.backups import BackupPicker, Backups
from services.backup_service import BackupEntry, BackupService


class BackupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.picker = BackupPicker()
        self.addCleanup(self.picker.close)
        self.picker.set_entries(
            [
                BackupEntry("cards/a.png", 100),
                BackupEntry("cards/b.png", 200),
                BackupEntry("coins/c.png", 300),
            ]
        )

    def test_all_category_and_manual_scopes(self):
        self.picker.category.setCurrentIndex(self.picker.category.findData("cards"))
        self.assertTrue(self.picker.table.isRowHidden(2))
        self.assertEqual(len(self.picker.names()), 3)
        self.picker.scope.setCurrentIndex(1)
        self.assertEqual(self.picker.names(), ["cards/a.png", "cards/b.png"])
        self.picker.scope.setCurrentIndex(2)
        self.picker.table.selectRow(1)
        self.assertEqual(self.picker.names(), ["cards/b.png"])
        self.picker.category.setCurrentIndex(self.picker.category.findData("coins"))
        self.assertEqual(self.picker.names(), [])

    def test_no_category_cannot_accidentally_target_everything(self):
        self.picker.scope.setCurrentIndex(1)
        self.assertEqual(self.picker.names(), [])

    def test_refresh_shows_new_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as folder:
            service = BackupService(folder)
            page = Backups(service)
            self.assertEqual(page.picker.entries, [])
            path = service.root / "background.png"
            path.write_bytes(b"backup")
            page.refresh()
            self.assertEqual(page.picker.names(), ["background.png"])
            path.unlink()
            page.refresh()
            self.assertEqual(page.picker.entries, [])
            page.close()


if __name__ == "__main__":
    unittest.main()
