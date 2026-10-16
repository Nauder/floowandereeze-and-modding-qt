"""Synthetic cut-in fixtures: no game payloads or private installation paths."""

from contextlib import closing
import base64
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import objects

with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
    from services import update_service

from services.backup_service import BackupService
from services.summon_animation_service import (
    Installation,
    SummonAnimationService,
    _Operation,
)
from unity.summon_metadata import COLUMNS, validate_row
from unity.summon_spine import (
    text_bytes,
    parse_atlas,
    validate_compatible,
    validate_image,
)

PREFIX = "assets/resourcesassetbundle/duel/timeline/duel/monstercutin/tcg/p123/sd/"
BIG_ID = "-9223372036854775000"
ATLAS = b"P123.png\nsize: 8,8\nformat: RGBA8888\npma: false\nregion\nbounds: 0,0,4,4\n\nPage2.png\nsize: 8,8\npma: false\nregion2\nbounds: 0,0,4,4\n"
SKELETON = json.dumps(
    {
        "skeleton": {"spine": "4.2.22"},
        "bones": [{"name": "root", "x": 0}],
        "slots": [{"name": "slot", "bone": "root", "attachment": "region"}],
        "skins": [{"name": "default", "attachments": {"slot": {"region": {"x": 0}}}}],
        "animations": {
            "animation": {"bones": {"root": {"translate": [{"time": 0, "x": 0}]}}}
        },
    }
).encode()


def row(role="texture", name="P123.png", bundle="00000001", path_id=BIG_ID, **changes):
    values = dict.fromkeys(COLUMNS)
    values.update(
        game_region="global",
        source="local",
        bundle=bundle,
        asset_path=PREFIX + name,
        card_id="123",
        display_name="Synthetic card",
        asset_region="tcg",
        quality="sd",
        scale=None,
        role=role,
        object_type="Texture2D" if role == "texture" else "TextAsset",
        path_id=path_id,
        serialized_file="CAB-" + bundle,
        asset_name="actual_" + name,
        width=8 if role == "texture" else None,
        height=8 if role == "texture" else None,
        external_references="[]",
    )
    values.update(changes)
    return values


def encode(value):
    return json.dumps(value, sort_keys=True).encode()


def image_bytes(color=(255, 0, 0, 255)):
    out = io.BytesIO()
    Image.new("RGBA", (8, 8), color).save(out, format="PNG")
    return out.getvalue()


class FakeObject:
    def __init__(self, descriptor, assets_file):
        self.original = descriptor
        self.assets_file = assets_file
        self.path_id = int(descriptor["id"])
        self.type = SimpleNamespace(name=descriptor["type"])
        self.data = None
        self.asset = SimpleNamespace(m_Name=descriptor["name"], save=self.save)
        if self.type.name == "Texture2D":
            self.asset.image = Image.open(
                io.BytesIO(base64.b64decode(descriptor["payload"]))
            ).copy()
            self.asset.m_Width, self.asset.m_Height = self.asset.image.size
            self.asset.m_TextureFormat = descriptor.get("format", 4)
            self.asset.m_MipCount = descriptor.get("mips", 1)
            self.asset.set_image = self.set_image
        else:
            self.asset.m_Script = base64.b64decode(descriptor["payload"]).decode(
                "utf-8", "surrogateescape"
            )

    def get_raw_data(self):
        return encode(self.original)

    def read(self):
        return self.asset

    def set_image(self, image, target_format, mipmap_count):
        self.asset.image = image.copy()
        self.asset.m_TextureFormat = target_format
        self.asset.m_MipCount = mipmap_count

    def save(self):
        updated = dict(self.original)
        if self.type.name == "Texture2D":
            out = io.BytesIO()
            self.asset.image.save(out, format="PNG")
            payload = out.getvalue()
            updated.update(
                format=self.asset.m_TextureFormat, mips=self.asset.m_MipCount
            )
        else:
            payload = text_bytes(self.asset)
        updated["payload"] = base64.b64encode(payload).decode()
        self.data = encode(updated)


def fake_load(payload):
    data = json.loads(payload)
    assets = {
        cab: SimpleNamespace(
            name=cab, externals=[SimpleNamespace(path=p) for p in refs]
        )
        for cab, refs in data["files"].items()
    }
    entries = [FakeObject(d, assets[d["cab"]]) for d in data["objects"]]
    env = SimpleNamespace(objects=entries)
    env.container = {
        d.original["path"]: SimpleNamespace(deref=lambda d=d: d, path_id=d.path_id)
        for d in entries
    }

    def save(**_):
        return encode(
            {
                "files": data["files"],
                "objects": [
                    json.loads(d.data) if d.data is not None else d.original
                    for d in entries
                ],
            }
        )

    env.file = SimpleNamespace(save=save)
    return env


def bundle(rows, payloads, references=None):
    return encode(
        {
            "files": {r["serialized_file"]: references or [] for r in rows},
            "objects": [
                {
                    "id": r["path_id"],
                    "type": r["object_type"],
                    "cab": r["serialized_file"],
                    "path": r["asset_path"],
                    "name": r["asset_name"],
                    "payload": base64.b64encode(payload).decode(),
                    **({"format": 4, "mips": 1} if r["role"] == "texture" else {}),
                }
                for r, payload in zip(rows, payloads)
            ],
        }
    )


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    def test_composite_refresh_is_idempotent_and_preserves_local_state(self):
        values = [
            row(),
            row(game_region="ocg"),
            row(source="streaming"),
            row(name="Other.png", path_id="9"),
        ]
        edit = models.SummonAnimationEditModel(
            installation="test",
            relative_path="local:00/00000001",
            manifest="original",
            modified=True,
        )
        self.session.add(edit)
        self.session.commit()
        for _ in range(2):
            update_service.update_summon_animations(DataFrame(values), self.session)
        self.session.commit()
        self.assertEqual(
            self.session.query(models.SummonAnimationAssetModel).count(), 4
        )
        self.assertEqual(
            self.session.query(models.SummonAnimationAssetModel).first().path_id, BIG_ID
        )
        self.assertTrue(edit.modified)
        values[0]["display_name"] = "Changed label"
        update_service.update_summon_animations(DataFrame(values), self.session)
        self.assertEqual(
            self.session.query(models.SummonAnimationAssetModel).first().display_name,
            "Changed label",
        )

    def test_caller_rollback_undoes_valid_refresh(self):
        update_service.update_summon_animations(DataFrame([row()]), self.session)
        self.session.rollback()
        self.assertEqual(
            self.session.query(models.SummonAnimationAssetModel).count(), 0
        )

    def test_malformed_late_row_rolls_back_entire_dataset(self):
        update_service.update_summon_animations(DataFrame([row()]), self.session)
        self.session.commit()
        changed = row(display_name="Must not be imported")
        invalid = row(name="invalid.png", animation_names="[1]")
        with self.assertRaises(ValueError):
            update_service.update_summon_animations(
                DataFrame([changed, invalid]), self.session
            )
        self.assertEqual(
            self.session.query(models.SummonAnimationAssetModel).one().display_name,
            "Synthetic card",
        )

    def test_empty_dataset_missing_schema_and_duplicate_identity(self):
        update_service.update_summon_animations(
            DataFrame(columns=COLUMNS), self.session
        )
        with self.assertRaises(ValueError):
            update_service.update_summon_animations(DataFrame(), self.session)
        with self.assertRaises(ValueError):
            update_service.update_summon_animations(
                DataFrame([row(), row()]), self.session
            )

    def test_optional_404_only_is_skipped(self):
        from requests import HTTPError, Response

        response = Response()
        response.status_code = 404
        with patch.object(
            update_service,
            "get_github_parquet_file",
            side_effect=HTTPError(response=response),
        ):
            self.assertFalse(
                update_service.update_summon_animations(db_session=self.session)
            )
        response.status_code = 500
        with patch.object(
            update_service,
            "get_github_parquet_file",
            side_effect=HTTPError(response=response),
        ):
            with self.assertRaises(HTTPError):
                update_service.update_summon_animations(db_session=self.session)

    def test_process_detection_fails_closed_and_distinguishes_the_game(self):
        from services.summon_animation_service import game_running

        with patch("services.summon_animation_service.subprocess.run") as process:
            process.return_value = SimpleNamespace(
                stdout='"other.exe","1","Console","1","100 K"'
            )
            self.assertFalse(game_running())
            process.return_value = SimpleNamespace(
                stdout='"masterduel.exe","1","Console","1","100 K"'
            )
            self.assertTrue(game_running())
            process.return_value = SimpleNamespace(stdout="")
            with self.assertRaises(RuntimeError):
                game_running()

    def test_roots_cannot_overlap_or_traverse(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                Installation("global", Path(folder), Path(folder) / "nested")
            installation = Installation("global", Path(folder))
            with self.assertRaises(ValueError):
                installation.path("local", "../other")

    def test_enum_numeric_ids_arrays_and_nullable_shared_rows(self):
        for change in (
            {"path_id": 9223372036854775000},
            {"source": "remote"},
            {"role": "guess"},
            {"asset_region": "global"},
            {"scale": "NaN"},
            {"width": 0},
            {"atlas_pages": "{}"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_row(row(**change))
        self.assertIsNone(validate_row(row(card_id=None, display_name=None))["card_id"])

    def test_existing_database_migration_is_additive_and_repeatable(self):
        import sqlite3
        from database.migrations import run_migrations

        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder) / "existing.db")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE app_config (id INTEGER PRIMARY KEY, game_path TEXT)"
                )
                connection.execute("INSERT INTO app_config VALUES (1, 'keep')")
                connection.commit()
            run_migrations(database)
            run_migrations(database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute("SELECT game_path FROM app_config").fetchall(),
                    [("keep",)],
                )
                names = {
                    r[0]
                    for r in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertTrue(
                    {"summon_animation_asset", "summon_animation_edit"} <= names
                )


class SpineTests(unittest.TestCase):
    def test_atlas_has_all_pages_and_out_of_bounds_is_rejected(self):
        self.assertEqual(
            [p["name"] for p in parse_atlas(ATLAS)], ["P123.png", "Page2.png"]
        )
        with self.assertRaises(ValueError):
            parse_atlas(ATLAS.replace(b"0,0,4,4", b"7,7,4,4"))

    def test_surrogateescape_round_trip(self):
        payload = b"\x00\xff\xfe\x80text"
        self.assertEqual(
            text_bytes(
                SimpleNamespace(m_Script=payload.decode("utf-8", "surrogateescape"))
            ),
            payload,
        )

    def test_exact_version_graph_and_timing_preserved(self):
        project = json.loads(SKELETON)
        project["bones"][0]["x"] = 5
        validate_compatible(SKELETON, json.dumps(project).encode(), ATLAS, ATLAS)
        for change in ("version", "bone", "time"):
            invalid = json.loads(SKELETON)
            if change == "version":
                invalid["skeleton"]["spine"] = "4.2.43"
            elif change == "bone":
                invalid["bones"][0]["name"] = "renamed"
            else:
                invalid["animations"]["animation"]["bones"]["root"]["translate"][0][
                    "time"
                ] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_compatible(
                    SKELETON, json.dumps(invalid).encode(), ATLAS, ATLAS
                )

    def test_missing_regions_and_unsupported_layout_changes(self):
        project = json.loads(SKELETON)
        project["skins"][0]["attachments"]["slot"]["region"]["path"] = "missing"
        with self.assertRaises(ValueError):
            validate_compatible(
                json.dumps(project).encode(), json.dumps(project).encode(), ATLAS, ATLAS
            )
        with self.assertRaises(ValueError):
            validate_compatible(
                SKELETON, SKELETON, ATLAS, ATLAS.replace(b"Page2.png", b"Renamed.png")
            )

    def test_pma_declaration_and_pixels(self):
        page = {"size": (8, 8), "pma": True}
        compatible = Image.new("RGBA", (8, 8), (40, 40, 40, 80))
        validate_image(compatible, page, "premultiplied")
        for image, alpha in (
            (compatible, "straight"),
            (Image.new("RGBA", (8, 8), (200, 0, 0, 80)), "premultiplied"),
        ):
            with self.assertRaises(ValueError):
                validate_image(image, page, alpha)
        with self.assertRaises(ValueError):
            validate_image(Image.new("RGBA", (4, 4)), page, "premultiplied")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.installation = Installation(
            "global", self.root / "local", self.root / "streaming"
        )
        self.texture = row()
        self.page2 = row(name="Page2.png", bundle="00000002", path_id="22")
        self.atlas = row(
            "atlas",
            "p123.atlas.txt",
            "00000003",
            "33",
            atlas_pages='["P123.png", "Page2.png"]',
        )
        self.skeleton = row(
            "skeleton_json",
            "p123js.json",
            "00000004",
            "44",
            spine_version="4.2.22",
            animation_names='["animation"]',
        )
        self.other = row("other", "unrelated.txt", "00000001", "55")
        self.rows = [self.texture, self.page2, self.atlas, self.skeleton, self.other]
        self.originals = {}
        self.write([self.texture, self.other], [image_bytes(), b"arbitrary\xff\x00"])
        self.write([self.page2], [image_bytes()])
        self.write([self.atlas], [ATLAS])
        self.write([self.skeleton], [SKELETON])
        self.service = SummonAnimationService(
            self.installation,
            self.rows,
            backup_root=self.root / "backups",
            loader=fake_load,
            running=lambda: False,
        )
        self.image = self.root / "replacement.png"
        self.image.write_bytes(image_bytes((0, 255, 0, 255)))

    def write(self, rows, payloads, refs=None):
        value = rows[0]
        path = self.installation.path(
            value["source"], f"{value['bundle'][:2]}/{value['bundle']}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bundle(rows, payloads, refs))
        self.originals[path] = path.read_bytes()
        return path

    def project(self):
        folder = self.root / "export"
        self.service.export_spine_project(self.rows, folder)
        return folder

    def test_browse_export_does_not_create_backup_or_change_bundles(self):
        self.service.preview_component(self.texture, self.rows)
        self.assertFalse((self.root / "backups").exists())
        destination = self.root / "raw.bin"
        self.service.export_component(self.other, destination)
        self.assertEqual(destination.read_bytes(), b"arbitrary\xff\x00")
        for path, payload in self.originals.items():
            self.assertEqual(path.read_bytes(), payload)

    def test_profile_scale_region_selection(self):
        hd = row(quality="highend_hd", scale="0.5")
        shared = row(quality=None)
        ocg = row(game_region="ocg")
        service = SummonAnimationService(
            self.installation, [self.texture, hd, shared, ocg]
        )
        selected = service.components("123", "tcg", "highend_hd", "0.5")
        self.assertEqual(selected, [hd, shared])

    def test_missing_wrong_region_and_stale_targets_are_refused(self):
        for change in (
            {"game_region": "ocg"},
            {"path_id": "2"},
            {"asset_name": "wrong"},
            {"serialized_file": "CAB-wrong"},
            {"object_type": "Material"},
            {"path_id": None},
            {"external_references": '["CAB-new"]'},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                _Operation(self.service).target({**self.texture, **change})
        self.service.resolve(self.page2).unlink()
        with self.assertRaises(FileNotFoundError):
            self.service.replace_texture(
                self.texture, self.rows, self.image, "straight"
            )
        self.assertFalse((self.root / "backups").exists())

    def test_multi_page_project_export_and_compatible_import(self):
        folder = self.project()
        self.assertTrue((folder / "Page2.png").exists())
        project = json.loads((folder / "skeleton.json").read_bytes())
        project["bones"][0]["x"] = 3
        (folder / "skeleton.json").write_bytes(json.dumps(project).encode())
        (folder / "P123.png").write_bytes(self.image.read_bytes())
        result = self.service.import_spine_project(self.rows, folder, "straight")
        self.assertEqual(len(result["manifests"]), 4)
        self.assertTrue(result["modified"])
        for path in result["manifests"]:
            self.assertTrue(Path(path).exists())
        self.service.restore_component_set(manifests=result["manifests"])
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_second_edits_keep_originals_shared_bundle_once(self):
        result = self.service.replace_texture(
            self.texture, self.rows, self.image, "straight"
        )
        self.assertEqual(len(result["manifests"]), 1)
        manifest = json.loads(Path(result["manifests"][0]).read_bytes())
        self.assertEqual(len(manifest["components"]), 2)
        self.image.write_bytes(image_bytes((0, 0, 255, 255)))
        second = self.service.replace_texture(
            self.texture, self.rows, self.image, "straight"
        )
        self.assertEqual(result["manifests"], second["manifests"])
        self.service.restore_component_set(manifests=second["manifests"])
        self.assertEqual(
            self.service.resolve(self.texture).read_bytes(),
            self.originals[self.service.resolve(self.texture)],
        )

    def test_incompatible_version_missing_page_and_layout_leave_files_untouched(self):
        folder = self.project()
        project = json.loads(SKELETON)
        project["skeleton"]["spine"] = "4.2.43"
        (folder / "skeleton.json").write_bytes(json.dumps(project).encode())
        with self.assertRaises(ValueError):
            self.service.import_spine_project(self.rows, folder, "straight")
        (folder / "skeleton.json").write_bytes(SKELETON)
        (folder / "Page2.png").unlink()
        with self.assertRaises(FileNotFoundError):
            self.service.import_spine_project(self.rows, folder, "straight")
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / "backups").exists())

    def test_dependency_byte_limit_refuses_before_writing(self):
        self.service.MAX_LOADED_BYTES = 1
        with self.assertRaises(ValueError):
            self.service.replace_texture(
                self.texture, self.rows, self.image, "straight"
            )
        self.assertFalse((self.root / "backups").exists())
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_missing_and_transitive_local_dependency_resolution(self):
        reference = "archive:/CAB-dependency/CAB-dependency"
        self.skeleton["external_references"] = json.dumps([reference])
        self.write([self.skeleton], [SKELETON], [reference])
        with self.assertRaises(ValueError):
            self.service.replace_texture(
                self.texture, self.rows, self.image, "straight"
            )
        dependency = row(
            "other",
            "shared.asset",
            "00000005",
            "77",
            serialized_file="CAB-dependency",
            card_id=None,
        )
        self.write([dependency], [b"shared"])
        self.service.replace_texture(self.texture, self.rows, self.image, "straight")

    def test_rollback_after_forced_second_file_failure(self):
        folder = self.project()
        real_replace = os.replace
        calls = []

        def replace(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError("forced second-file failure")
            return real_replace(source, destination)

        with patch("services.summon_animation_service.os.replace", side_effect=replace):
            with self.assertRaises(OSError):
                self.service.import_spine_project(self.rows, folder, "straight")
        self.assertGreaterEqual(len(calls), 3)
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob("tmp*")), [])

    def test_zip_round_trip_and_corrupt_backup(self):
        result = self.service.replace_texture(
            self.texture, self.rows, self.image, "straight"
        )
        backup = self.service.backups
        names = [e.name for e in backup.inventory()]
        archive = self.root / "backups.zip"
        backup.export_archive(archive, names)
        imported = BackupService(self.root / "imported")
        imported.import_archive(archive, names)
        for name in names:
            self.assertEqual(
                backup._path(name).read_bytes(), imported._path(name).read_bytes()
            )
        original = Path(result["manifests"][0]).parent / "original.bundle"
        original.write_bytes(b"corrupted")
        live = self.service.resolve(self.texture).read_bytes()
        with self.assertRaises(ValueError):
            self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(self.service.resolve(self.texture).read_bytes(), live)

    def test_game_running_blocks_writes_and_restore(self):
        self.service.running = lambda: True
        with self.assertRaises(RuntimeError):
            self.service.replace_texture(
                self.texture, self.rows, self.image, "straight"
            )
        with self.assertRaises(RuntimeError):
            self.service.restore_component_set(rows=[self.texture])
        self.assertFalse((self.root / "backups").exists())

    def test_format_mips_and_unrelated_object_are_preserved(self):
        original = _Operation(self.service).target(self.other)[1].get_raw_data()
        self.service.replace_texture(self.texture, self.rows, self.image, "straight")
        operation = _Operation(self.service)
        self.assertEqual(operation.target(self.other)[1].get_raw_data(), original)
        texture = operation.target(self.texture)[2]
        self.assertEqual((texture.m_TextureFormat, texture.m_MipCount), (4, 1))

    def test_ambiguous_pages_and_exports_inside_game_are_rejected(self):
        duplicate = {**self.page2, "source": "streaming"}
        service = SummonAnimationService(
            self.installation, self.rows + [duplicate], loader=fake_load
        )
        with self.assertRaises(ValueError):
            service.preview_component(self.texture, self.rows + [duplicate])
        with self.assertRaises(ValueError):
            self.service.export_component(
                self.texture, self.service.resolve(self.texture)
            )

    def test_real_unity_container_helper_and_ambiguous_paths(self):
        from UnityPy.helpers.ContainerHelper import ContainerHelper

        env = fake_load(self.service.resolve(self.texture).read_bytes())
        original = list(env.container.items())
        env.container = ContainerHelper(
            [(name, SimpleNamespace(asset=pointer)) for name, pointer in original]
        )
        operation = _Operation(self.service)
        self.assertEqual(operation.target(self.texture, env)[1].path_id, int(BIG_ID))
        env.container.container.append(
            (original[0][0], SimpleNamespace(asset=original[0][1]))
        )
        with self.assertRaises(ValueError):
            operation.target(self.texture, env)

    def test_restore_survives_metadata_moving_a_component(self):
        result = self.service.replace_texture(
            self.texture, self.rows, self.image, "straight"
        )
        self.texture["bundle"] = "11111111"
        entries = self.service.backup_inventory()
        self.assertEqual(len(entries), 1)
        self.service.restore_component_set(manifests=result["manifests"])
        path = self.installation.path("local", "00/00000001")
        self.assertEqual(path.read_bytes(), self.originals[path])

    def test_load_each_physical_bundle_once_and_full_precision_ids(self):
        calls = []
        self.service.loader = lambda payload: (
            calls.append(payload),
            fake_load(payload),
        )[1]
        operation = _Operation(self.service)
        obj = operation.target(self.texture)[1]
        operation.target(self.other)
        self.assertEqual(len(calls), 1)
        self.assertEqual(str(obj.path_id), BIG_ID)


if __name__ == "__main__":
    unittest.main()
