"""Regression checks for full-art gate edits, including shared-file isolation."""

import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.full_art_service import FullArtService
from util.card_art import decode_full_art_entries, set_full_art_entry


def pairs(*entries):
    return b"".join(struct.pack("<HH", *entry) for entry in entries)


class FullArtFormatTests(unittest.TestCase):
    def test_first_pair_is_never_mistaken_for_a_length_header(self):
        data = pairs((1, 0), (22811, 17069))
        self.assertEqual(decode_full_art_entries(data), [(1, 0), (22811, 17069)])

    def test_remove_preserves_order_base_ids_and_unrelated_duplicates(self):
        data = pairs((3105, 0), (22811, 17069), (3105, 0), (22811, 17069))
        self.assertEqual(set_full_art_entry(data, 22811), pairs((3105, 0), (3105, 0)))

    def test_restore_does_not_override_a_new_live_mapping(self):
        data = pairs((22811, 123))
        self.assertEqual(set_full_art_entry(data, 22811, (22811, 17069)), data)

    def test_malformed_data_and_invalid_ids_are_rejected(self):
        for data in (b"x", b"xxx", b"xxxxx"):
            with self.assertRaises(ValueError):
                decode_full_art_entries(data)
        for art_id in (0, -1, 65536):
            with self.assertRaises(ValueError):
                set_full_art_entry(b"", art_id)


class FullArtServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        previous = os.getcwd()
        os.chdir(self.temporary.name)
        self.addCleanup(os.chdir, previous)
        self.game_path = str(Path("game").resolve())
        self.path = Path(self.game_path) / "0000" / "22" / "22817d01"
        self.path.parent.mkdir(parents=True)
        self.original = pairs((22811, 17069), (3105, 0))
        self.path.write_bytes(self.original)
        self.service = FullArtService()

        def load(payload):
            asset = SimpleNamespace(
                m_Name="of_card_asset",
                m_Script=payload.decode("utf-8", "surrogateescape"),
                save=lambda: None,
            )
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        type=SimpleNamespace(name="TextAsset"), read=lambda: asset
                    )
                ],
                file=SimpleNamespace(
                    save=lambda **_: asset.m_Script.encode("utf-8", "surrogateescape")
                ),
            )

        patcher = patch("services.full_art_service.unity_load", side_effect=load)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disable_and_restore_after_restart_preserve_other_mods(self):
        self.assertEqual(self.service.status(self.game_path, 22811), (True, True))
        self.service.set_enabled(self.game_path, 22811, False, "LZ4")
        self.assertEqual(self.path.read_bytes(), pairs((3105, 0)))
        self.assertEqual(self.service.status(self.game_path, 22811), (False, True))
        self.path.write_bytes(pairs((3105, 0), (99, 42)))
        restarted = FullArtService()
        restarted.set_enabled(self.game_path, 22811, True, "LZ4")
        self.assertEqual(
            self.path.read_bytes(), pairs((3105, 0), (99, 42), (22811, 17069))
        )

    def test_normal_card_can_be_enabled_disabled_and_reenabled_after_restart(self):
        self.assertEqual(self.service.status(self.game_path, 50), (False, True))
        self.service.set_enabled(self.game_path, 50, True, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original + pairs((50, 50)))
        self.assertEqual(self.service.status(self.game_path, 50), (True, True))
        self.service.set_enabled(self.game_path, 50, True, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original + pairs((50, 50)))
        self.service.set_enabled(self.game_path, 50, False, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original)
        restarted = FullArtService()
        restarted.set_enabled(self.game_path, 50, True, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original + pairs((50, 50)))

    def test_invalid_texture_ids_cannot_be_enabled(self):
        for art_id in (0, -1, 65536):
            self.assertEqual(
                self.service.status(self.game_path, art_id), (False, False)
            )
            with self.assertRaises(ValueError):
                self.service.set_enabled(self.game_path, art_id, True, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_atomic_replace_failure_leaves_live_bundle_unchanged(self):
        with patch(
            "services.full_art_service.os.replace", side_effect=OSError("locked")
        ):
            with self.assertRaises(OSError):
                self.service.set_enabled(self.game_path, 22811, False, "LZ4")
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_malformed_gate_is_never_written(self):
        self.path.write_bytes(b"invalid")
        with self.assertRaises(RuntimeError):
            self.service.set_enabled(self.game_path, 22811, False, "LZ4")
        self.assertEqual(self.path.read_bytes(), b"invalid")


if __name__ == "__main__":
    unittest.main()
