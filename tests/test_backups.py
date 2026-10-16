"""Backup archive integrity, selection, and containment regression checks."""

import tempfile
import unittest
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZipInfo

from services.backup_service import BackupService


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.service = BackupService(self.root / "backups")

    def put(self, name, content=b"original"):
        path = self.service.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def archive(self, members):
        archive = self.root / "import.zip"
        with ZipFile(archive, "w") as output:
            for name, content in members:
                member = ZipInfo()
                member.filename = name
                output.writestr(member, content)
        return archive

    def test_round_trip_everything_including_nested_and_background(self):
        names = ["cards/a.png", "cards/full_art/account/a.bytes", "ShopBGBase02.png"]
        for name in names:
            self.put(name, name.encode())
        archive = self.root / "export.zip"
        self.assertEqual(self.service.export_archive(archive, names), 3)
        target = BackupService(self.root / "new")
        self.assertEqual(target.import_archive(archive, names), (3, 0))
        self.assertEqual(self.service.inventory(), target.inventory())
        for name in names:
            self.assertEqual((target.root / name).read_bytes(), name.encode())

    def test_selected_export_and_delete_leave_other_files(self):
        self.put("cards/a.png")
        self.put("coins/b.png")
        archive = self.root / "export.zip"
        self.service.export_archive(archive, ["cards/a.png"])
        self.assertEqual(
            [entry.name for entry in self.service.inspect_archive(archive)],
            ["cards/a.png"],
        )
        self.assertEqual(self.service.delete(["cards/a.png"]), 1)
        self.assertEqual(
            [entry.name for entry in self.service.inventory()], ["coins/b.png"]
        )

    def test_import_selection_and_conflict_policy(self):
        self.put("cards/a.png")
        archive = self.archive([("cards/a.png", b"changed"), ("coins/b.png", b"coin")])
        self.assertEqual(self.service.import_archive(archive, ["cards/a.png"]), (0, 1))
        self.assertEqual((self.service.root / "cards/a.png").read_bytes(), b"original")
        self.assertFalse((self.service.root / "coins/b.png").exists())
        self.assertEqual(
            self.service.import_archive(archive, ["cards/a.png"], True), (1, 0)
        )
        self.assertEqual((self.service.root / "cards/a.png").read_bytes(), b"changed")

    def test_unsafe_archives_never_write(self):
        for name in [
            "../escape.png",
            "/escape.png",
            "C:/escape.png",
            "cards\\escape.png",
            "cards/NUL.png",
            "cards/a:stream",
            "cards/trailing.",
        ]:
            with self.subTest(name=name):
                archive = self.archive([("cards/a.png", b"safe"), (name, b"unsafe")])
                with self.assertRaises(ValueError):
                    self.service.import_archive(archive, ["cards/a.png"])
                self.assertFalse(self.service.root.exists())

    def test_duplicate_and_conflicting_paths_rejected(self):
        for members in [
            [("cards/a.png", b"a"), ("cards/A.png", b"b")],
            [("cards", b"a"), ("cards/a.png", b"b")],
        ]:
            with self.assertRaises(ValueError):
                self.service.inspect_archive(self.archive(members))

    def test_failed_export_preserves_previous_archive(self):
        archive = self.root / "export.zip"
        archive.write_bytes(b"previous export")
        with self.assertRaises(OSError):
            self.service.export_archive(archive, ["cards/missing.png"])
        self.assertEqual(archive.read_bytes(), b"previous export")

    def test_delete_cannot_escape_root(self):
        with self.assertRaises(ValueError):
            self.service.delete(["../outside"])

    def test_corrupt_later_file_prevents_all_import_writes(self):
        archive = self.archive(
            [
                ("cards/a.png", b"safe original"),
                ("coins/b.png", b"unique backup payload"),
            ]
        )
        archive.write_bytes(
            archive.read_bytes().replace(
                b"unique backup payload", b"broken backup payload"
            )
        )
        with self.assertRaises(BadZipFile):
            self.service.import_archive(archive, ["cards/a.png", "coins/b.png"])
        self.assertFalse(self.service.root.exists())

    def test_archive_limits_and_symbolic_links_rejected(self):
        archive = self.archive([("cards/a.png", b"large")])
        self.service.MAX_ARCHIVE_SIZE = 1
        with self.assertRaises(ValueError):
            self.service.inspect_archive(archive)
        self.service.MAX_ARCHIVE_SIZE = 4 * 1024**3
        member = ZipInfo("cards/link.png")
        member.create_system = 3
        member.external_attr = 0o120777 << 16
        with ZipFile(archive, "w") as output:
            output.writestr(member, "../../outside")
        with self.assertRaises(ValueError):
            self.service.inspect_archive(archive)


if __name__ == "__main__":
    unittest.main()
