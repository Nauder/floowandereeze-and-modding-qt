"""Deck box dimension, backup, and variant selection regression checks."""

import os
import tempfile
import unittest
from pathlib import Path
from struct import unpack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image
from sqlalchemy import create_engine
from database import objects

with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
with patch("database.migrations.run_migrations"):
    from services import deck_box_service


class DeckBoxTests(unittest.TestCase):
    def test_native_dimensions_and_other_objects(self):
        service = deck_box_service.DeckBoxService()
        service.bundle = "12345678"
        texture = MagicMock(m_Width=128, m_Height=192)
        obj = MagicMock()
        obj.type.name = "Texture2D"
        obj.path_id = 42
        obj.read.return_value = texture
        other = MagicMock()
        other.type.name = "Material"
        env = MagicMock(objects=[other, obj])
        env.file.save.return_value = b"bundle"
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "source.png")
            Image.new("RGBA", (300, 300), (255, 0, 0, 128)).save(source)
            service.image_path = str(source)
            bundle = Path(folder, "bundle")
            with (
                patch.object(
                    deck_box_service, "prepare_environment", return_value=str(bundle)
                ),
                patch.object(deck_box_service, "unity_load", return_value=env),
                patch.object(
                    service, "_expand_sprites", wraps=service._expand_sprites
                ) as expand,
            ):
                service.replace_bundle()
                expand.assert_called_once_with(env, 42, (128, 192))
            self.assertEqual(bundle.read_bytes(), b"bundle")
        image = texture.set_image.call_args.kwargs["img"]
        self.assertEqual(image.size, (128, 192))
        self.assertEqual(image.mode, "RGBA")
        other.read.assert_not_called()
        texture.save.assert_called_once()

    def test_sprite_mesh_covers_full_rect_at_every_resolution(self):
        for _, fields in deck_box_service.DECK_BOX_VARIANTS:
            for field in fields:
                with self.subTest(field=field):
                    size = 512 if "large" in field else 256
                    sprite = {
                        "m_Rect": {"x": 0.0, "y": 0.0, "width": size, "height": size},
                        "m_Pivot": {"x": 0.25, "y": 0.75},
                        "m_PixelsToUnits": 100.0,
                        "m_RD": {
                            "texture": {"m_FileID": 0, "m_PathID": 42},
                            "settingsRaw": 64,
                            "m_VertexData": {
                                "m_Channels": [
                                    dict(stream=0, offset=0, format=0, dimension=0)
                                    for _ in range(14)
                                ],
                            },
                            "m_SubMeshes": [{}],
                        },
                    }
                    obj = MagicMock()
                    obj.type.name = "Sprite"
                    obj.read_typetree.return_value = sprite
                    deck_box_service.DeckBoxService._expand_sprites(
                        SimpleNamespace(objects=[obj]), 42, (size, size)
                    )
                    obj.save_typetree.assert_called_once_with(sprite)
                    render = sprite["m_RD"]
                    vertices = render["m_VertexData"]
                    self.assertEqual(vertices["m_VertexCount"], 4)
                    positions = unpack("<12f", vertices["m_DataSize"][:48])
                    for actual, expected in zip(
                        positions,
                        (
                            -size * 0.25 / 100,
                            -size * 0.75 / 100,
                            0,
                            -size * 0.25 / 100,
                            size * 0.25 / 100,
                            0,
                            size * 0.75 / 100,
                            size * 0.25 / 100,
                            0,
                            size * 0.75 / 100,
                            -size * 0.75 / 100,
                            0,
                        ),
                    ):
                        self.assertAlmostEqual(actual, expected, places=6)
                    self.assertEqual(
                        unpack("<8f", vertices["m_DataSize"][48:]),
                        (0, 0, 0, 1, 1, 1, 1, 0),
                    )
                    self.assertEqual(
                        unpack("<6H", bytes(render["m_IndexBuffer"])),
                        (0, 1, 2, 0, 2, 3),
                    )
                    self.assertEqual(render["textureRect"], sprite["m_Rect"])
                    self.assertEqual(render["textureRectOffset"], {"x": 0, "y": 0})
                    self.assertEqual(render["settingsRaw"], 0)
                    self.assertEqual(render["m_SubMeshes"][0]["indexCount"], 6)
                    self.assertEqual(render["m_SubMeshes"][0]["vertexCount"], 4)
                    self.assertEqual(sprite["m_Pivot"], {"x": 0.25, "y": 0.75})

    def test_sprite_geometry_only_updates_the_replaced_texture(self):
        for reference in (
            {"m_FileID": 0, "m_PathID": 99},
            {"m_FileID": 1, "m_PathID": 42},
        ):
            with self.subTest(reference=reference):
                obj = MagicMock()
                obj.type.name = "Sprite"
                obj.read_typetree.return_value = {"m_RD": {"texture": reference}}
                deck_box_service.DeckBoxService._expand_sprites(
                    SimpleNamespace(objects=[obj]), 42, (512, 512)
                )
                obj.save_typetree.assert_not_called()

    def test_backups_independent_and_not_overwritten(self):
        service = deck_box_service.DeckBoxService()
        with (
            patch.object(
                deck_box_service.Path, "is_file", side_effect=[False, True, False]
            ),
            patch.object(service, "create_backup") as backup,
        ):
            service.bundle = "large"
            service.ensure_backup()
            service.ensure_backup()
            service.bundle = "o_large"
            service.ensure_backup()
        self.assertEqual(
            [call.args for call in backup.call_args_list], [("large",), ("o_large",)]
        )

    def test_missing_texture_never_writes(self):
        service = deck_box_service.DeckBoxService()
        service.bundle, service.image_path = "bundle", "source"
        with (
            patch.object(
                deck_box_service, "prepare_environment", return_value="unused"
            ),
            patch.object(
                deck_box_service, "unity_load", return_value=SimpleNamespace(objects=[])
            ),
            patch("builtins.open") as opened,
        ):
            with self.assertRaises(ValueError):
                service.replace_bundle()
        opened.assert_not_called()

    def test_restore_retains_source_on_failure(self):
        service = deck_box_service.DeckBoxService()
        service.bundle, service.image_path = "bundle", "source"
        with (
            patch.object(deck_box_service.Path, "is_file", return_value=True),
            patch.object(service, "_replace_texture", side_effect=OSError),
        ):
            with self.assertRaises(OSError):
                service.restore_asset()
        self.assertEqual(service.image_path, "source")

    def test_orientation_replaces_all_matching_resolutions(self):
        asset = SimpleNamespace(
            small="small",
            medium="medium",
            large="large",
            r_medium="left_medium",
            r_large="left_large",
            o_medium="open_medium",
            o_large="open_large",
        )
        service = deck_box_service.DeckBoxService()
        service.image_path = "source"
        for _, fields in deck_box_service.DECK_BOX_VARIANTS:
            service.select_variant(asset, fields)
            expected = [getattr(asset, field) for field in fields]
            self.assertEqual(service.bundle, expected[-1])
            with patch.object(service, "_replace_texture") as replace:
                service.replace_bundle()
            self.assertEqual(
                [call.args for call in replace.call_args_list],
                [(bundle, "source") for bundle in expected],
            )

    def test_group_restore_uses_each_original_and_requires_all_backups(self):
        service = deck_box_service.DeckBoxService()
        service.bundles = ("small", "medium", "large")
        service.bundle, service.image_path = "large", "source"
        with (
            patch.object(deck_box_service.Path, "is_file", return_value=True),
            patch.object(service, "_replace_texture") as replace,
        ):
            self.assertTrue(service.restore_variant())
        self.assertEqual(
            [call.args for call in replace.call_args_list],
            [
                (bundle, str(Path("backups", "deck_boxes", bundle + ".png")))
                for bundle in service.bundles
            ],
        )
        self.assertEqual(service.image_path, "source")
        with (
            patch.object(deck_box_service.Path, "is_file", side_effect=[True, False]),
            patch.object(service, "_replace_texture") as replace,
        ):
            self.assertFalse(service.restore_variant())
        replace.assert_not_called()

    def test_bulk_restore_only_changes_requested_bundle(self):
        service = deck_box_service.DeckBoxService()
        service.bundles = ("small", "medium", "large")
        service.bundle = "large"
        with (
            patch.object(deck_box_service.Path, "is_file", return_value=True),
            patch.object(service, "_replace_texture") as replace,
        ):
            self.assertTrue(service.restore_asset())
        replace.assert_called_once_with(
            "large", str(Path("backups", "deck_boxes", "large.png"))
        )

    def test_copy_and_backup_cover_group_and_retain_display_bundle(self):
        service = deck_box_service.DeckBoxService()
        service.bundles = ("medium", "large")
        service.bundle = "large"
        with (
            patch.object(deck_box_service.Path, "is_file", return_value=False),
            patch.object(service, "create_backup") as backup,
        ):
            service.ensure_backup()
        self.assertEqual(
            [call.args for call in backup.call_args_list], [("medium",), ("large",)]
        )
        self.assertEqual(service.bundle, "large")
        copied = []
        with patch.object(
            service,
            "create_bundle_copy",
            side_effect=lambda: copied.append(service.bundle),
        ):
            service.copy_bundle()
        self.assertEqual(copied, ["medium", "large"])
        self.assertEqual(service.bundle, "large")

    def test_variant_selection_and_source_enable_replacement(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon, QPixmap
        from pages.deck_box import DeckBox

        app = QApplication.instance() or QApplication([])
        with (
            patch("pages.models.deck_box_list_model.DeckBoxListModel.refresh"),
            patch(
                "pages.models.deck_box_list_model.DeckBoxListModel.get_names",
                return_value=[],
            ),
            patch("pages.deck_box.QSettings") as settings,
        ):
            settings.return_value.value.return_value = None
            page = DeckBox()
        self.assertFalse(page.replaceButton.isEnabled())
        self.assertEqual(page.variantBox.count(), 3)
        self.assertEqual(
            [page.variantBox.itemText(i) for i in range(3)],
            ["Normal", "Left Facing", "Open"],
        )
        asset = SimpleNamespace(name="Test box", favorite=False)
        for _, fields in deck_box_service.DECK_BOX_VARIANTS:
            for key in fields:
                setattr(asset, key, key + "_bundle")
        page.model.assets = [asset]
        icon = QIcon(QPixmap(128, 192))
        asset.thumb = icon
        with (
            patch.object(page.service, "texture_size", return_value=(128, 192)),
            patch("pages.deck_box.fetch_bundle_thumb", return_value=icon),
        ):
            page._on_deck_box_clicked(page.model.index(0, 0))
            self.assertEqual(page.service.bundle, "large_bundle")
            self.assertFalse(page.replaceButton.isEnabled())
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder, "image.png")
                Image.new("RGBA", (300, 300)).save(source)
                page._set_image(str(source))
                self.assertTrue(page.replaceButton.isEnabled())
                page.variantBox.setCurrentIndex(2)
                self.assertEqual(page.service.bundle, "o_large_bundle")
                self.assertEqual(
                    page.service.bundles, ("o_medium_bundle", "o_large_bundle")
                )
                page.variantBox.setCurrentIndex(1)
                self.assertEqual(page.service.bundle, "r_large_bundle")
                self.assertEqual(page._texture_size, (128, 192))
        page.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
