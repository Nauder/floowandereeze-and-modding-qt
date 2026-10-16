"""GIF timing, atlas generation and transactional flipbook regression tests."""

import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import test_summon_animations as fixtures
from services.summon_animation_service import Installation, SummonAnimationService
from unity.summon_frames import (
    FrameOptions,
    ImportMemoryWarning,
    decode_frames,
    sample_frames,
    generate_project,
)
from unity.summon_spine import parse_atlas, validate_compatible


def png(size=(32, 32), color=(255, 80, 0, 128)):
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, format="PNG")
    return out.getvalue()


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_png_natural_order_alpha_and_fit_crop(self):
        for name, color in (
            ("10.png", (0, 0, 255, 128)),
            ("2.png", (0, 255, 0, 128)),
            ("1.png", (255, 0, 0, 128)),
        ):
            (self.root / name).write_bytes(png((32, 16), color))
        frames, delays = decode_frames(self.root, FrameOptions(edge=32, png_fps=20), 1)
        self.assertEqual(
            [f.getpixel((16, 16)) for f in frames],
            [(255, 0, 0, 128), (0, 255, 0, 128), (0, 0, 255, 128)],
        )
        self.assertEqual(delays, [0.05] * 3)
        self.assertEqual(frames[0].getpixel((0, 0))[3], 0)
        cropped, _ = decode_frames(self.root, FrameOptions(edge=32, framing="crop"), 1)
        self.assertEqual(cropped[0].getpixel((0, 0))[3], 128)

    def test_gif_composition_and_individual_delays(self):
        images = [
            Image.new("RGBA", (32, 32), (255, 0, 0, 255)),
            Image.new("RGBA", (32, 32), (0, 255, 0, 255)),
        ]
        path = self.root / "animation.gif"
        images[0].save(
            path,
            save_all=True,
            append_images=images[1:],
            duration=[100, 300],
            disposal=2,
        )
        frames, delays = decode_frames(path, FrameOptions(edge=32), 1)
        self.assertEqual(delays, [0.1, 0.3])
        _, indices, times = sample_frames(frames, delays, 1, FrameOptions(fps=4))
        self.assertEqual(indices, [0, 1, 1, 1])
        self.assertEqual(times, [0, 0.25, 0.5, 0.75])

    def test_gif_disposal_removes_previous_frame_and_keeps_transparency(self):
        palette = [0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (768 - 9)
        frames = []
        for position, color in ((0, 1), (16, 2)):
            image = Image.new("P", (32, 32), 0)
            image.putpalette(palette)
            image.paste(color, (position, 0, position + 8, 8))
            frames.append(image)
        path = self.root / "transparent.gif"
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            transparency=0,
            disposal=2,
            optimize=False,
        )
        decoded, _ = decode_frames(path, FrameOptions(edge=32), 1)
        self.assertEqual(decoded[0].getpixel((1, 1)), (255, 0, 0, 255))
        self.assertEqual(decoded[1].getpixel((1, 1))[3], 0)
        self.assertEqual(decoded[1].getpixel((17, 1)), (0, 255, 0, 255))

    def test_source_speed_trim_and_hold(self):
        frames = [Image.new("RGBA", (32, 32)) for _ in range(2)]
        _, indices, _ = sample_frames(
            frames, [0.1, 0.1], 1, FrameOptions(fps=4, timing="source")
        )
        self.assertEqual(indices, [0, 1, 1, 1])
        _, indices, _ = sample_frames(
            frames, [1, 1], 0.5, FrameOptions(fps=4, timing="source")
        )
        self.assertEqual(indices, [0, 0])

    def test_capacity_multipage_pma_gutters_events_and_exact_end(self):
        original = json.loads(fixtures.SKELETON)
        original["skeleton"].update(x=-50, y=-60, width=100, height=120)
        original["events"] = {"hit": {"int": 1}}
        original["animations"]["animation"]["events"] = [{"time": 0.1, "name": "hit"}]
        pages = [
            {"name": "a.png", "size": (40, 40), "pma": True},
            {"name": "b.png", "size": (40, 40), "pma": False},
        ]
        frames = [Image.new("RGBA", (32, 32), (255, 80, 0, 128)) for _ in range(2)]
        payload, atlas, sheets = generate_project(
            original, pages, frames, [0, 1], [0, 0.5], 1, FrameOptions(edge=32)
        )
        project = json.loads(payload)
        self.assertEqual(
            project["animations"]["animation"]["slots"]["frames"]["attachment"][-1],
            {"time": 1, "name": "floo_frame_0001"},
        )
        self.assertEqual(project["events"], original["events"])
        self.assertEqual(
            project["animations"]["animation"]["events"],
            original["animations"]["animation"]["events"],
        )
        self.assertEqual(sheets[0].getpixel((2, 2)), (128, 40, 0, 128))
        self.assertEqual(sheets[0].getpixel((0, 0)), sheets[0].getpixel((2, 2)))
        self.assertEqual(len(parse_atlas(atlas)), 2)
        with self.assertRaisesRegex(ValueError, "atlas cells"):
            generate_project(
                original, pages[:1], frames, [0, 1], [0, 0.5], 1, FrameOptions()
            )
        with self.assertRaises(ValueError):
            validate_compatible(fixtures.SKELETON, payload, fixtures.ATLAS, atlas)

    def test_lazy_large_atlases_allocate_only_frame_patches(self):
        from unity.summon_frames import AtlasSheet

        original = json.loads(fixtures.SKELETON)
        original["skeleton"].update(width=100, height=100)
        pages = [
            {"name": f"page{i}.png", "size": (8192, 8192), "pma": False}
            for i in range(2)
        ]
        frames = [Image.new("RGBA", (32, 32), (255, 80, 0, 128))]
        with patch("unity.summon_frames.Image.new", wraps=Image.new) as allocate:
            _, atlas, sheets = generate_project(
                original, pages, frames, [0], [0], 1, FrameOptions(edge=32), lazy=True
            )
        self.assertTrue(
            all(
                call.args[1][0] * call.args[1][1] <= 36**2
                for call in allocate.call_args_list
            )
        )
        self.assertTrue(all(isinstance(sheet, AtlasSheet) for sheet in sheets))
        self.assertEqual([sheet.size for sheet in sheets], [(8192, 8192)] * 2)
        self.assertEqual([len(sheet.patches) for sheet in sheets], [1, 0])
        self.assertEqual(len(parse_atlas(atlas)), 2)
        pages[0]["size"] = (8192, 8193)
        with self.assertRaisesRegex(ValueError, "atlas page exceeds"):
            generate_project(
                original, pages, frames, [0], [0], 1, FrameOptions(), lazy=True
            )

    def test_lazy_sheet_keeps_pma_gutters_and_transparent_unused_pages(self):
        original = json.loads(fixtures.SKELETON)
        original["skeleton"].update(width=100, height=100)
        pages = [
            {"name": f"page{i}.png", "size": (40, 40), "pma": True} for i in range(2)
        ]
        frames = [Image.new("RGBA", (32, 32), (255, 80, 0, 128))]
        _, _, sheets = generate_project(
            original, pages, frames, [0], [0], 1, FrameOptions(edge=32), lazy=True
        )
        with sheets[0].render() as image:
            self.assertEqual(image.getpixel((2, 2)), (128, 40, 0, 128))
            self.assertEqual(image.getpixel((0, 0)), (128, 40, 0, 128))
            self.assertEqual(image.getpixel((39, 39)), (0, 0, 0, 0))
        with sheets[1].render() as image:
            self.assertIsNone(image.getbbox())

    def test_invalid_input_and_limits(self):
        (self.root / "fake.png").write_bytes(b"not an image")
        with self.assertRaises(OSError):
            decode_frames(self.root, FrameOptions(), 1)
        with self.assertRaises(ValueError):
            FrameOptions(fps=0).validate()
        with self.assertRaises(ValueError):
            sample_frames(
                [Image.new("RGBA", (1, 1))], [1], float("nan"), FrameOptions()
            )
        path = self.root / "disguised.gif"
        path.write_bytes(png())
        with self.assertRaisesRegex(ValueError, "Expected GIF"):
            decode_frames(path, FrameOptions(), 1)

    def test_large_png_sequence_warns_before_conversion_and_allows_override(self):
        for index in range(33):
            (self.root / f"frame{index}.png").write_bytes(png())
        with patch("PIL.Image.Image.convert") as convert:
            with self.assertRaisesRegex(
                ImportMemoryWarning, "Estimated working memory"
            ):
                decode_frames(self.root, FrameOptions(edge=1024), 1)
        convert.assert_not_called()
        # Approving the import passes the preflight gate, before frame conversion.
        with patch("PIL.Image.Image.convert", side_effect=RuntimeError("conversion")):
            with self.assertRaisesRegex(RuntimeError, "conversion"):
                decode_frames(
                    self.root, FrameOptions(edge=1024), 1, allow_large_import=True
                )

    def test_large_gif_warns_before_conversion(self):
        path = self.root / "animation.gif"
        images = [Image.new("RGB", (32, 32), (i * 7, 0, 0)) for i in range(33)]
        for image in images:
            self.addCleanup(image.close)
        images[0].save(path, save_all=True, append_images=images[1:], duration=100)
        with patch("PIL.Image.Image.convert") as convert:
            with self.assertRaises(ImportMemoryWarning):
                decode_frames(path, FrameOptions(edge=1024), 1)
        convert.assert_not_called()


class GraphFixture:
    """Complete SD/HD playback graph with two HD pages and unrelated bytes."""

    def __init__(self, root):
        self.root = Path(root)
        self.installation = Installation("global", self.root / "game")
        self.rows, self.hidden, self.payloads = [], [], {}
        self.next_id = 100
        self.profiles = []
        for quality, count in (("sd", 1), ("highend_hd", 2)):
            profile = {}
            for role in (
                "skeleton_json",
                "atlas",
                "skeleton_data",
                "atlas_asset",
                "prefab",
            ):
                kind = (
                    "TextAsset"
                    if role in {"skeleton_json", "atlas"}
                    else "Mesh" if role == "prefab" else "MonoBehaviour"
                )
                profile[role] = self.add(role, quality, kind)
            profile["textures"] = [
                self.add(
                    "texture",
                    quality,
                    "Texture2D",
                    f"page{i}.png",
                    width=128,
                    height=128,
                )
                for i in range(count)
            ]
            profile["materials"] = [
                self.add("material", quality, "Material", f"mat{i}")
                for i in range(count)
            ]
            self.profiles.append(profile)
        self.reference = self.add("animation", None, "MonoBehaviour")
        self.timeline = self.add("timeline", None, "MonoBehaviour")
        self.unrelated = self.add(
            "other",
            "sd",
            "TextAsset",
            "unrelated",
            bundle=self.profiles[0]["atlas"]["bundle"],
        )
        self.payloads[self.unrelated["path_id"]] = b"unchanged arbitrary bytes\xff"
        self.cabs = list(dict.fromkeys(r["serialized_file"] for r in self.rows))
        for row in self.rows:
            refs = [cab for cab in self.cabs if cab != row["serialized_file"]]
            row["external_references"] = json.dumps(refs)
        for profile in self.profiles:
            skeleton = json.loads(fixtures.SKELETON)
            skeleton["skeleton"].update(x=-50, y=-50, width=100, height=100)
            skeleton["skins"][0]["attachments"]["slot"]["region"]["path"] = "region0"
            self.payloads[profile["skeleton_json"]["path_id"]] = json.dumps(
                skeleton
            ).encode()
            profile["skeleton_json"]["spine_version"] = "4.2.22"
            profile["skeleton_json"]["animation_names"] = '["animation"]'
            atlas = "\n\n".join(
                f"page{i}.png\nsize: 128,128\npma: true\nregion{i}\nbounds: 0,0,32,32"
                for i in range(len(profile["textures"]))
            )
            self.payloads[profile["atlas"]["path_id"]] = atlas.encode()
            self.payloads[profile["prefab"]["path_id"]] = b"mesh geometry unchanged"
            for texture in profile["textures"]:
                self.payloads[texture["path_id"]] = png((128, 128))
            for material, texture in zip(profile["materials"], profile["textures"]):
                self.tree(
                    material,
                    {
                        "m_SavedProperties": {
                            "m_TexEnvs": [
                                [
                                    "_MainTex",
                                    {"m_Texture": self.pointer(material, texture)},
                                ]
                            ],
                            "m_Floats": [["_StraightAlphaInput", 0]],
                        }
                    },
                )
            data = profile["skeleton_data"]
            atlas_asset = profile["atlas_asset"]
            self.mono(
                data,
                "SkeletonDataAsset",
                "Spine.Unity",
                {
                    "skeletonJSON": self.pointer(data, profile["skeleton_json"]),
                    "atlasAssets": [self.pointer(data, atlas_asset)],
                    "skeletonDataModifiers": [],
                    "blendModeMaterials": {},
                },
            )
            self.mono(
                atlas_asset,
                "SpineAtlasAsset",
                "Spine.Unity",
                {
                    "atlasFile": self.pointer(atlas_asset, profile["atlas"]),
                    "materials": [
                        self.pointer(atlas_asset, m) for m in profile["materials"]
                    ],
                },
            )
            behaviour = self.add(
                "other",
                profile["prefab"]["quality"],
                "MonoBehaviour",
                "renderer",
                bundle=profile["prefab"]["bundle"],
                hidden=True,
            )
            self.mono(
                behaviour,
                "SkeletonAnimation",
                "Spine.Unity",
                {
                    "skeletonDataAsset": self.pointer(behaviour, data),
                    "initialSkinName": "",
                    "separatorSlotNames": [],
                },
            )
        self.mono(
            self.reference,
            "AnimationReferenceAsset",
            "Spine.Unity",
            {
                "skeletonDataAsset": self.pointer(
                    self.reference, self.profiles[0]["skeleton_data"]
                ),
                "animationName": "animation",
            },
        )
        self.track = self.add(
            "other",
            None,
            "MonoBehaviour",
            "track",
            bundle=self.timeline["bundle"],
            hidden=True,
        )
        self.clip = self.add(
            "other",
            None,
            "MonoBehaviour",
            "clip",
            bundle=self.timeline["bundle"],
            hidden=True,
        )
        self.mono(
            self.timeline,
            "TimelineAsset",
            "UnityEngine.Timeline",
            {"m_Tracks": [self.pointer(self.timeline, self.track)]},
        )
        self.mono(
            self.track,
            "SpineAnimationStateTrack",
            "Spine.Unity.Playables",
            {
                "m_Children": [],
                "m_Clips": [
                    {
                        "m_Start": 0,
                        "m_ClipIn": 0,
                        "m_TimeScale": 1,
                        "m_Duration": 1,
                        "m_Asset": self.pointer(self.track, self.clip),
                    }
                ],
            },
        )
        self.mono(
            self.clip,
            "SpineAnimationStateClip",
            "Spine.Unity.Playables",
            {
                "template": {
                    "animationReference": self.pointer(self.clip, self.reference),
                    "loop": 0,
                }
            },
        )
        self.write()
        self.originals = {
            p: p.read_bytes() for p in self.installation.local_root.glob("??/????????")
        }
        self.service = SummonAnimationService(
            self.installation,
            self.rows,
            loader=self.load,
            running=lambda: False,
            backup_root=self.root / "backups",
        )
        self.source = self.root / "frames"
        self.source.mkdir()
        for i in range(3):
            (self.source / f"frame{i}.png").write_bytes(
                png(color=(255, i * 70, 0, 128))
            )

    def add(self, role, quality, kind, name=None, bundle=None, hidden=False, **kwargs):
        self.next_id += 1
        row = fixtures.row(
            role,
            name or role,
            bundle or f"{self.next_id:08x}",
            str(self.next_id),
            quality=quality,
            object_type=kind,
            **kwargs,
        )
        row["asset_path"] = row["asset_path"].replace(
            "/sd/", f"/{quality or 'shared'}/"
        )
        (self.hidden if hidden else self.rows).append(row)
        return row

    def pointer(self, origin, target):
        refs = [cab for cab in self.cabs if cab != origin["serialized_file"]]
        return {
            "m_FileID": (
                0
                if origin["serialized_file"] == target["serialized_file"]
                else refs.index(target["serialized_file"]) + 1
            ),
            "m_PathID": int(target["path_id"]),
        }

    def tree(self, row, tree):
        self.payloads[row["path_id"]] = json.dumps(tree).encode()

    def mono(self, row, cls, namespace, tree):
        script = self.add(
            "other",
            row["quality"],
            "MonoScript",
            "script_" + str(self.next_id),
            bundle=row["bundle"],
            hidden=True,
        )
        self.tree(script, {"m_ClassName": cls, "m_Namespace": namespace})
        self.tree(row, dict(tree, m_Script=self.pointer(row, script)))

    def write(self):
        groups = {}
        for row in self.rows + self.hidden:
            groups.setdefault(row["bundle"], []).append(row)
        for number, rows in groups.items():
            path = self.installation.path("local", f"{number[:2]}/{number}")
            path.parent.mkdir(parents=True, exist_ok=True)
            refs = [cab for cab in self.cabs if cab != rows[0]["serialized_file"]]
            path.write_bytes(
                fixtures.bundle(rows, [self.payloads[r["path_id"]] for r in rows], refs)
            )

    @staticmethod
    def load(payload):
        env = fixtures.fake_load(payload)
        for obj in env.objects:
            obj.read_typetree = lambda obj=obj: json.loads(obj.asset.m_Script)

            def save_typetree(tree, obj=obj):
                obj.asset.m_Script = json.dumps(tree)
                obj.save()

            obj.save_typetree = save_typetree
        return env


class FrameServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = GraphFixture(self.temp.name)
        self.service = self.fixture.service
        self.options = FrameOptions(edge=32, fps=10, png_fps=3)

    def prepare(self):
        return self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options
        )

    def embedded_animation_copy(self, bundle=None, use_prefab_root=False):
        bundle = bundle or self.fixture.timeline["bundle"]
        project = self.fixture.add(
            "other", None, "TextAsset", "embedded_json", bundle=bundle, hidden=True
        )
        self.fixture.payloads[project["path_id"]] = self.fixture.payloads[
            self.fixture.profiles[0]["skeleton_json"]["path_id"]
        ]
        data = self.fixture.add(
            "other", None, "MonoBehaviour", "embedded_data", bundle=bundle, hidden=True
        )
        self.fixture.mono(
            data,
            "SkeletonDataAsset",
            "Spine.Unity",
            {
                "skeletonJSON": self.fixture.pointer(data, project),
                "atlasAssets": [
                    self.fixture.pointer(data, self.fixture.profiles[0]["atlas_asset"])
                ],
                "skeletonDataModifiers": [],
            },
        )
        reference = self.fixture.reference
        tree = json.loads(self.fixture.payloads[reference["path_id"]])
        tree["skeletonDataAsset"] = self.fixture.pointer(reference, data)
        self.fixture.tree(reference, tree)
        if use_prefab_root:
            track = self.fixture.add(
                "other",
                None,
                "MonoBehaviour",
                "embedded_track",
                bundle=bundle,
                hidden=True,
            )
            clip = self.fixture.add(
                "other",
                None,
                "MonoBehaviour",
                "embedded_clip",
                bundle=bundle,
                hidden=True,
            )
            root = self.fixture.add(
                "other",
                None,
                "MonoBehaviour",
                "embedded_root",
                bundle=bundle,
                hidden=True,
            )
            self.fixture.mono(
                clip,
                "SpineAnimationStateClip",
                "Spine.Unity.Playables",
                {
                    "template": {
                        "animationReference": self.fixture.pointer(clip, reference),
                        "loop": 0,
                    }
                },
            )
            self.fixture.mono(
                track,
                "SpineAnimationStateTrack",
                "Spine.Unity.Playables",
                {
                    "m_Children": [],
                    "m_Clips": [
                        {
                            "m_Start": 0,
                            "m_ClipIn": 0,
                            "m_TimeScale": 1,
                            "m_Duration": 1,
                            "m_Asset": self.fixture.pointer(track, clip),
                        }
                    ],
                },
            )
            self.fixture.mono(
                root,
                "TimelineAsset",
                "UnityEngine.Timeline",
                {"m_Tracks": [self.fixture.pointer(root, track)]},
            )
            self.fixture.rows.remove(self.fixture.timeline)
            self.fixture.hidden.append(self.fixture.timeline)
            self.service.rows = [dict(row) for row in self.fixture.rows]
        self.fixture.write()
        return project

    def test_embedded_animation_copy_receives_shared_frame_timelines_and_restores(self):
        row = self.embedded_animation_copy()
        before = {p: p.read_bytes() for p in self.fixture.originals}
        result = self.service.apply_frame_animation(self.prepare())
        env = self.service.loader(
            self.service.resolve(self.fixture.timeline).read_bytes()
        )
        obj = next(o for o in env.objects if str(o.path_id) == row["path_id"])
        copied = json.loads(fixtures.text_bytes(obj.read()))
        high = self.decoded_project(self.fixture.profiles[1])
        self.assertEqual(copied["animations"], high["animations"])
        self.assertEqual(copied["slots"], high["slots"])
        self.assertTrue(
            all(
                a["type"] == "point"
                for a in copied["skins"][0]["attachments"][
                    "floo_frames_highend_hd"
                ].values()
            )
        )
        self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_prefab_embedded_timeline_without_exported_timeline_supported(self):
        row = self.embedded_animation_copy(
            self.fixture.profiles[1]["prefab"]["bundle"], True
        )
        plan = self.prepare()
        self.service.apply_frame_animation(plan)
        env = self.service.loader(
            self.service.resolve(self.fixture.profiles[1]["prefab"]).read_bytes()
        )
        obj = next(o for o in env.objects if str(o.path_id) == row["path_id"])
        project = json.loads(fixtures.text_bytes(obj.read()))
        self.assertIn(
            "floo_frames_highend_hd", project["animations"]["animation"]["slots"]
        )

    def test_incompatible_embedded_copy_rejected_before_writes(self):
        row = self.embedded_animation_copy()
        tree = json.loads(self.fixture.payloads[row["path_id"]])
        tree["bones"].append({"name": "unrelated", "parent": "root"})
        self.fixture.tree(row, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "incompatible playback structures"):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_embedded_changes_after_preview_rejected(self):
        row = self.embedded_animation_copy()
        plan = self.prepare()
        project = json.loads(self.fixture.payloads[row["path_id"]])
        project["skeleton"]["hash"] = "changed"
        self.fixture.tree(row, project)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            self.service.apply_frame_animation(plan)

    def test_cross_quality_slot_override_reset_when_renderer_or_texture_replaced(self):
        custom = self.add_custom_materials()
        tree = json.loads(self.fixture.payloads[custom["path_id"]])
        tree["customSlotMaterials"][0]["material"] = self.fixture.pointer(
            custom, self.fixture.profiles[0]["materials"][0]
        )
        self.fixture.tree(custom, tree)
        self.fixture.write()
        path = self.service.resolve(self.fixture.profiles[1]["prefab"])
        original = path.read_bytes()
        metadata_before = json.loads(json.dumps(self.service.rows))
        low = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.assertIn("both quality modes", low["quality_warning"])
        low_result = self.service.apply_frame_animation(low)
        self.assertNotEqual(path.read_bytes(), original)
        plan = self.prepare()
        self.assertEqual(self.service.rows, metadata_before)
        self.service = SummonAnimationService(
            self.fixture.installation,
            metadata_before,
            loader=self.fixture.load,
            running=lambda: False,
            backup_root=self.fixture.root / "backups",
        )
        result = self.service.apply_frame_animation(plan)
        env = self.service.loader(path.read_bytes())
        obj = next(o for o in env.objects if str(o.path_id) == custom["path_id"])
        actual = obj.read_typetree()
        self.assertEqual(actual["customSlotMaterials"][0]["overrideDisabled"], 1)
        tree["customSlotMaterials"][0]["overrideDisabled"] = 1
        self.assertEqual(actual, tree)
        self.service.restore_component_set(
            manifests=low_result["manifests"] + result["manifests"]
        )
        self.assertEqual(path.read_bytes(), original)

    def test_root_transform_and_sprite_color_effects_preserved(self):
        clip = self.add_effect_track()
        original = json.loads(self.fixture.payloads[clip["path_id"]])
        for type_id, attribute in ((4, 1), (4, 2), (4, 3), (4, 4), (212, 304273561)):
            with self.subTest(type_id=type_id, attribute=attribute):
                tree = json.loads(json.dumps(original))
                binding = tree["m_ClipBindingConstant"]["genericBindings"][0]
                binding.update(
                    typeID=type_id, customType=0, path=0, attribute=attribute
                )
                tree["m_HasGenericRootTransform"] = type_id == 4
                self.fixture.tree(clip, tree)
                self.fixture.write()
                path = self.service.resolve(self.fixture.timeline)
                before = path.read_bytes()
                result = self.service.apply_frame_animation(self.prepare())
                self.assertEqual(path.read_bytes(), before)
                self.service.restore_component_set(manifests=result["manifests"])

    def test_nonroot_and_noncolor_numeric_bindings_rejected(self):
        clip = self.add_effect_track()
        original = json.loads(self.fixture.payloads[clip["path_id"]])
        for type_id, attribute, path in ((4, 1, 123), (4, 9, 0), (212, 3305885265, 0)):
            with self.subTest(type_id=type_id, attribute=attribute, path=path):
                tree = json.loads(json.dumps(original))
                tree["m_ClipBindingConstant"]["genericBindings"][0].update(
                    typeID=type_id, customType=0, path=path, attribute=attribute
                )
                self.fixture.tree(clip, tree)
                self.fixture.write()
                with self.assertRaisesRegex(
                    ValueError, "unsupported renderer/script bindings"
                ):
                    self.prepare()

    def test_duplicate_profile_export_follows_renderer_and_updates_reference_only_json(
        self,
    ):
        low = self.fixture.profiles[0]
        data = self.fixture.add(
            "skeleton_data",
            "sd",
            "MonoBehaviour",
            "unscaled_data",
            bundle=low["skeleton_data"]["bundle"],
        )
        project = self.fixture.add(
            "skeleton_json",
            "sd",
            "TextAsset",
            "unscaled_json",
            bundle=low["skeleton_json"]["bundle"],
        )
        self.fixture.payloads[project["path_id"]] = self.fixture.payloads[
            low["skeleton_json"]["path_id"]
        ]
        project.update(spine_version="4.2.22", animation_names='["animation"]')
        for row, original in (
            (data, low["skeleton_data"]),
            (project, low["skeleton_json"]),
        ):
            row["external_references"] = original["external_references"]
        self.fixture.mono(
            data,
            "SkeletonDataAsset",
            "Spine.Unity",
            {
                "skeletonJSON": self.fixture.pointer(data, project),
                "atlasAssets": [{"m_FileID": 0, "m_PathID": 0}],
                "skeletonDataModifiers": [],
            },
        )
        tree = json.loads(self.fixture.payloads[self.fixture.reference["path_id"]])
        tree["skeletonDataAsset"] = self.fixture.pointer(self.fixture.reference, data)
        self.fixture.tree(self.fixture.reference, tree)
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        plan = self.prepare()
        self.assertEqual(
            plan["quality_bindings"], {"sd": "sd", "highend_hd": "highend_hd"}
        )
        self.service.apply_frame_animation(plan)
        env = self.service.loader(self.service.resolve(project).read_bytes())
        obj = next(o for o in env.objects if str(o.path_id) == project["path_id"])
        actual = json.loads(fixtures.text_bytes(obj.read()))
        self.assertIn(
            "floo_frames_highend_hd", actual["animations"]["animation"]["slots"]
        )

    def test_embedded_json_does_not_require_an_exported_container_entry(self):
        row = self.embedded_animation_copy()
        original_loader = self.service.loader

        def load(payload):
            env = original_loader(payload)
            env.container = {
                name: ptr
                for name, ptr in env.container.items()
                if str(ptr.deref().path_id) != row["path_id"]
            }
            return env

        self.service.loader = load
        self.service.apply_frame_animation(self.prepare())

    def add_timeline_variant(self, duration=1, name="animation", data=None):
        root = self.fixture.add("timeline", None, "MonoBehaviour", "variant_timeline")
        self.fixture.cabs.append(root["serialized_file"])
        for row in self.fixture.rows:
            row["external_references"] = json.dumps(
                [cab for cab in self.fixture.cabs if cab != row["serialized_file"]]
            )
        track = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "variant_track",
            bundle=root["bundle"],
            hidden=True,
        )
        clip = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "variant_clip",
            bundle=root["bundle"],
            hidden=True,
        )
        reference = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "variant_reference",
            bundle=self.fixture.reference["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            reference,
            "AnimationReferenceAsset",
            "Spine.Unity",
            {
                "skeletonDataAsset": self.fixture.pointer(
                    reference, data or self.fixture.profiles[1]["skeleton_data"]
                ),
                "animationName": name,
            },
        )
        self.fixture.mono(
            clip,
            "SpineAnimationStateClip",
            "Spine.Unity.Playables",
            {
                "template": {
                    "animationReference": self.fixture.pointer(clip, reference),
                    "loop": 0,
                }
            },
        )
        self.fixture.mono(
            track,
            "SpineAnimationStateTrack",
            "Spine.Unity.Playables",
            {
                "m_Children": [],
                "m_Clips": [
                    {
                        "m_Start": 0,
                        "m_ClipIn": 0,
                        "m_TimeScale": 1,
                        "m_Duration": duration,
                        "m_Asset": self.fixture.pointer(track, clip),
                    }
                ],
            },
        )
        self.fixture.mono(
            root,
            "TimelineAsset",
            "UnityEngine.Timeline",
            {
                "m_Tracks": [self.fixture.pointer(root, track)],
            },
        )
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        return root

    def test_separate_quality_timelines_preserved_with_both_quality_selections(self):
        variant = self.add_timeline_variant()
        timeline_paths = [
            self.service.resolve(row) for row in (self.fixture.timeline, variant)
        ]
        original = {path: path.read_bytes() for path in timeline_paths}
        for lower_quality in (False, True):
            with self.subTest(lower_quality=lower_quality):
                plan = self.service.prepare_frame_animation(
                    self.fixture.rows,
                    self.fixture.source,
                    self.options,
                    lower_quality=lower_quality,
                )
                self.assertEqual(plan["duration"], 1)
                self.service.apply_frame_animation(plan)
                self.assertEqual(
                    original, {path: path.read_bytes() for path in timeline_paths}
                )

    def test_separate_timeline_duration_mismatch_rejected(self):
        self.add_timeline_variant(duration=0.9)
        with self.assertRaisesRegex(
            ValueError, "variants must have the same bounded duration"
        ):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_separate_timeline_animation_mismatch_rejected(self):
        self.add_timeline_variant(name="other")
        with self.assertRaisesRegex(
            ValueError, "variants must select the same animation name"
        ):
            self.prepare()

    def test_separate_timeline_unknown_skeleton_rejected(self):
        self.add_timeline_variant(data=self.fixture.profiles[0]["atlas_asset"])
        with self.assertRaisesRegex(ValueError, "does not match converted profiles"):
            self.prepare()

    def split_playback(self):
        tree = json.loads(self.fixture.payloads[self.fixture.track["path_id"]])
        first = dict(tree["m_Clips"][0], m_Duration=0.4)
        second = dict(first, m_Start=0.4, m_ClipIn=0.4, m_Duration=0.6)
        tree["m_Clips"] = [second, first]
        self.fixture.tree(self.fixture.track, tree)
        self.fixture.write()
        return tree

    def add_parallel_track(self, name="animation", data=None):
        reference = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "parallel_reference",
            bundle=self.fixture.reference["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            reference,
            "AnimationReferenceAsset",
            "Spine.Unity",
            {
                "skeletonDataAsset": self.fixture.pointer(
                    reference, data or self.fixture.profiles[1]["skeleton_data"]
                ),
                "animationName": name,
            },
        )
        track = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "parallel_track",
            bundle=self.fixture.timeline["bundle"],
            hidden=True,
        )
        clip = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "parallel_clip",
            bundle=self.fixture.timeline["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            clip,
            "SpineAnimationStateClip",
            "Spine.Unity.Playables",
            {
                "template": {
                    "animationReference": self.fixture.pointer(clip, reference),
                    "loop": 0,
                }
            },
        )
        self.fixture.mono(
            track,
            "SpineAnimationStateTrack",
            "Spine.Unity.Playables",
            {
                "m_Children": [],
                "m_Clips": [
                    {
                        "m_Start": 0,
                        "m_ClipIn": 0,
                        "m_TimeScale": 1,
                        "m_Duration": 1,
                        "m_Asset": self.fixture.pointer(track, clip),
                    }
                ],
            },
        )
        root = json.loads(self.fixture.payloads[self.fixture.timeline["path_id"]])
        root["m_Tracks"].append(self.fixture.pointer(self.fixture.timeline, track))
        self.fixture.tree(self.fixture.timeline, root)
        self.fixture.write()
        return track, reference

    def test_continuous_split_clips_keep_duration_and_timeline_bytes(self):
        self.split_playback()
        path = self.service.resolve(self.fixture.timeline)
        original = path.read_bytes()
        plan = self.prepare()
        self.assertEqual(plan["duration"], 1)
        self.service.apply_frame_animation(plan)
        self.assertEqual(path.read_bytes(), original)
        project = self.decoded_project(self.fixture.profiles[1])
        keys = project["animations"]["animation"]["slots"]["floo_frames_highend_hd"][
            "attachment"
        ]
        self.assertEqual(keys[-1]["time"], 1)

    def test_split_gaps_overlaps_offsets_and_retiming_rejected(self):
        original = self.split_playback()
        for field, value, message in (
            ("m_Start", 0.5, "continuous"),
            ("m_Start", 0.3, "continuous"),
            ("m_ClipIn", 0, "Offset or retimed"),
            ("m_TimeScale", 2, "Offset or retimed"),
        ):
            with self.subTest(field=field, value=value):
                tree = json.loads(json.dumps(original))
                tree["m_Clips"][0][field] = value
                if field == "m_Start":
                    tree["m_Clips"][0]["m_ClipIn"] = value
                self.fixture.tree(self.fixture.track, tree)
                self.fixture.write()
                with self.assertRaisesRegex(ValueError, message):
                    self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_split_clips_with_different_reference_rejected(self):
        track, _ = self.add_parallel_track()
        second = json.loads(self.fixture.payloads[track["path_id"]])["m_Clips"][0]
        tree = self.split_playback()
        tree["m_Clips"][0]["m_Asset"] = second["m_Asset"]
        self.fixture.tree(self.fixture.track, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "same animation reference"):
            self.prepare()

    def test_parallel_quality_tracks_preserve_timeline_and_unselected_images(self):
        self.add_parallel_track()
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.prepare()
        self.assertEqual(plan["duration"], 1)
        self.service.apply_frame_animation(plan)
        self.assert_image_files_unchanged(self.fixture.profiles[0], before)
        path = self.service.resolve(self.fixture.timeline)
        self.assertEqual(path.read_bytes(), before[path])

    def test_parallel_duration_mismatch_rejected(self):
        track, _ = self.add_parallel_track()
        tree = json.loads(self.fixture.payloads[track["path_id"]])
        tree["m_Clips"][0]["m_Duration"] = 0.9
        self.fixture.tree(track, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "same bounded duration"):
            self.prepare()

    def test_parallel_animation_name_and_unverified_data_rejected(self):
        _, reference = self.add_parallel_track(name="other")
        with self.assertRaisesRegex(ValueError, "same animation name"):
            self.prepare()
        tree = json.loads(self.fixture.payloads[reference["path_id"]])
        tree["animationName"] = "animation"
        tree["skeletonDataAsset"] = self.fixture.pointer(
            reference, self.fixture.profiles[0]["atlas_asset"]
        )
        self.fixture.tree(reference, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "does not match converted profiles"):
            self.prepare()

    def test_disconnected_parallel_track_rejected(self):
        self.add_parallel_track()
        tree = json.loads(self.fixture.payloads[self.fixture.timeline["path_id"]])
        tree["m_Tracks"].pop()
        self.fixture.tree(self.fixture.timeline, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "not connected"):
            self.prepare()

    def test_resized_atlases_rebuilt_at_texture_size_only_for_selected_quality(self):
        from services.summon_animation_service import _Operation

        low, high = self.fixture.profiles
        for profile, size in ((low, 96), (high, 256)):
            key = profile["atlas"]["path_id"]
            self.fixture.payloads[key] = self.fixture.payloads[key].replace(
                b"size: 128,128", f"size: {size},{size}".encode()
            )
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "dimensions disagree"):
            self.service._atlas(
                [r for r in self.fixture.rows if r["quality"] == "sd"],
                _Operation(self.service),
            )
        before = {p: p.read_bytes() for p in self.fixture.originals}
        self.service.apply_frame_animation(self.prepare())
        self.assert_image_files_unchanged(low, before)
        env = self.service.loader(self.service.resolve(high["atlas"]).read_bytes())
        pages = parse_atlas(
            fixtures.text_bytes(
                env.container[high["atlas"]["asset_path"]].deref().read()
            )
        )
        self.assertEqual([page["size"] for page in pages], [(128, 128)] * 2)
        plan = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.service.apply_frame_animation(plan)
        env = self.service.loader(self.service.resolve(low["atlas"]).read_bytes())
        pages = parse_atlas(
            fixtures.text_bytes(
                env.container[low["atlas"]["asset_path"]].deref().read()
            )
        )
        self.assertEqual(pages[0]["size"], (128, 128))

    def test_unbound_helper_renderer_preserved_but_cannot_supply_playback(self):
        profile = self.fixture.profiles[1]
        helper = self.fixture.add(
            "other",
            "highend_hd",
            "MonoBehaviour",
            "empty_renderer",
            bundle=profile["prefab"]["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            helper,
            "SkeletonAnimation",
            "Spine.Unity",
            {
                "skeletonDataAsset": {"m_FileID": 0, "m_PathID": 0},
                "_animationName": "",
            },
        )
        original = self.fixture.payloads[helper["path_id"]]
        self.fixture.write()
        self.service.apply_frame_animation(self.prepare())
        env = self.service.loader(self.service.resolve(helper).read_bytes())
        obj = next(o for o in env.objects if str(o.path_id) == helper["path_id"])
        self.assertEqual(obj.read_typetree(), json.loads(original))
        tree = json.loads(original)
        tree["_animationName"] = "animation"
        self.fixture.tree(helper, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "Unbound renderer"):
            self.prepare()

    def test_empty_and_identical_slot_overrides_preserved(self):
        custom = self.add_custom_materials()
        tree = json.loads(self.fixture.payloads[custom["path_id"]])
        tree["customSlotMaterials"].extend(
            [
                dict(tree["customSlotMaterials"][0]),
                {
                    "overrideDisabled": 0,
                    "slotName": "",
                    "material": {"m_FileID": 0, "m_PathID": 0},
                },
            ]
        )
        self.fixture.tree(custom, tree)
        original = self.fixture.payloads[custom["path_id"]]
        self.fixture.write()
        self.service.apply_frame_animation(self.prepare())
        env = self.service.loader(self.service.resolve(custom).read_bytes())
        obj = next(o for o in env.objects if str(o.path_id) == custom["path_id"])
        self.assertEqual(obj.read_typetree(), json.loads(original))

    def test_conflicting_duplicate_slot_overrides_rejected(self):
        custom = self.add_custom_materials()
        tree = json.loads(self.fixture.payloads[custom["path_id"]])
        duplicate = dict(tree["customSlotMaterials"][0])
        duplicate["material"] = self.fixture.pointer(
            custom, self.fixture.profiles[1]["materials"][1]
        )
        tree["customSlotMaterials"].append(duplicate)
        self.fixture.tree(custom, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "Conflicting custom material"):
            self.prepare()

    def test_partial_empty_slot_overrides_rejected(self):
        custom = self.add_custom_materials()
        original = self.fixture.payloads[custom["path_id"]]
        for field, value in (
            ("slotName", ""),
            ("material", {"m_FileID": 0, "m_PathID": 0}),
        ):
            tree = json.loads(original)
            tree["customSlotMaterials"][0][field] = value
            self.fixture.tree(custom, tree)
            self.fixture.write()
            with self.assertRaises(ValueError):
                self.prepare()

    def add_infinite_effect(self):
        clip = self.add_effect_track()
        track = next(
            r for r in self.fixture.hidden if r["asset_name"] == "actual_effect_track"
        )
        tree = json.loads(self.fixture.payloads[track["path_id"]])
        tree["m_Clips"] = []
        tree["m_InfiniteClip"] = self.fixture.pointer(track, clip)
        self.fixture.tree(track, tree)
        self.fixture.write()
        return clip

    def shared_timeline_container(self, clip):
        clip["asset_path"] = self.fixture.timeline["asset_path"]
        clip["role"] = "timeline"
        clip["external_references"] = self.fixture.timeline["external_references"]
        self.fixture.hidden.remove(clip)
        self.fixture.rows.append(clip)
        self.service.rows = [dict(r) for r in self.fixture.rows]
        self.fixture.write()

        class Container(dict):
            def __init__(self, env):
                self.entries = [
                    (obj.original["path"], SimpleNamespace(deref=lambda obj=obj: obj))
                    for obj in env.objects
                ]
                super().__init__(self.entries)

            def items(self):
                return self.entries

        def load(payload):
            env = self.fixture.load(payload)
            env.container = Container(env)
            return env

        self.service.loader = load

    def test_timeline_curve_subasset_resolves_root_and_preserves_bundle(self):
        clip = self.add_infinite_effect()
        self.shared_timeline_container(clip)
        # Exercise metadata containing only the curve export, and both exports.
        for only_curve in (False, True):
            with self.subTest(only_curve=only_curve):
                self.service.rows = [
                    dict(r)
                    for r in self.fixture.rows
                    if not only_curve or r is not self.fixture.timeline
                ]
                before = self.service.resolve(clip).read_bytes()
                plan = self.service.prepare_frame_animation(
                    self.service.rows, self.fixture.source, self.options
                )
                self.service.apply_frame_animation(plan)
                self.assertEqual(self.service.resolve(clip).read_bytes(), before)

    def test_ambiguous_timeline_roots_rejected(self):
        clip = self.add_infinite_effect()
        extra = self.fixture.add(
            "other",
            None,
            "MonoBehaviour",
            "extra_root",
            bundle=self.fixture.timeline["bundle"],
            hidden=True,
        )
        extra["asset_path"] = self.fixture.timeline["asset_path"]
        self.fixture.mono(
            extra, "TimelineAsset", "UnityEngine.Timeline", {"m_Tracks": []}
        )
        self.shared_timeline_container(clip)
        with self.assertRaisesRegex(ValueError, "exactly one timeline root"):
            self.prepare()

    def test_subasset_metadata_identity_must_match(self):
        from services.summon_animation_service import _Operation

        clip = self.add_infinite_effect()
        self.shared_timeline_container(clip)
        stale = dict(clip, path_id="987654321")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            _Operation(self.service).target(stale)

    def test_infinite_effect_rejects_events_and_non_material_bindings(self):
        clip = self.add_infinite_effect()
        original = self.fixture.payloads[clip["path_id"]]
        for mode in ("event", "pointer", "transform"):
            tree = json.loads(original)
            binding = tree["m_ClipBindingConstant"]["genericBindings"][0]
            if mode == "event":
                tree["m_Events"] = [{"functionName": "unsafe"}]
            elif mode == "pointer":
                binding["isPPtrCurve"] = 1
            else:
                binding["typeID"] = 4
            self.fixture.tree(clip, tree)
            self.fixture.write()
            with self.assertRaisesRegex(ValueError, "Auxiliary animation"):
                self.prepare()

    def effect_shader(self, name="TimelineShader/SM/SM_FogShader"):
        profile = self.fixture.profiles[1]
        material = profile["materials"][0]
        shader = self.fixture.add(
            "other",
            "highend_hd",
            "Shader",
            "effect_shader",
            bundle=material["bundle"],
            hidden=True,
        )
        state = {
            "m_Name": "Universal Forward",
            "rtBlend0": {
                "srcBlend": {"val": 5, "name": "<noninit>"},
                "destBlend": {"val": 10, "name": "<noninit>"},
                "blendOp": {"val": 0, "name": "<noninit>"},
            },
        }
        self.fixture.tree(
            shader,
            {
                "m_ParsedForm": {
                    "m_Name": name,
                    "m_SubShaders": [{"m_Passes": [{"m_State": state}]}],
                }
            },
        )
        tree = json.loads(self.fixture.payloads[material["path_id"]])
        tree["m_Shader"] = self.fixture.pointer(material, shader)
        tree["m_SavedProperties"]["m_Floats"] = []
        self.fixture.tree(material, tree)
        key = profile["atlas"]["path_id"]
        self.fixture.payloads[key] = self.fixture.payloads[key].replace(
            b"pma: true\n", b""
        )
        self.fixture.write()
        return shader

    def test_effect_shader_alpha_verified_and_other_page_stays_pma(self):
        from services.summon_animation_service import _Operation
        from unity.summon_flipbook_graph import FlipbookGraph

        shader = self.effect_shader()
        profiles, _, _, _ = FlipbookGraph(
            self.service, _Operation(self.service), self.fixture.rows
        ).validate()
        high = next(p for p in profiles if p[1]["quality"] == "highend_hd")
        self.assertEqual([p["pma"] for p in high[5]], [False, True])
        before = self.service.resolve(shader).read_bytes()
        self.service.apply_frame_animation(self.prepare())
        self.assertEqual(self.service.resolve(shader).read_bytes(), before)

    def test_fire_and_shake_effect_shaders_preserve_materials_and_straight_alpha(self):
        for name in (
            "TimelineShader/SM/SM_Fire_Shader",
            "TimelineShader/SM/SM_Shake_Shader",
        ):
            with self.subTest(shader=name):
                shader = self.effect_shader(name)
                before = self.service.resolve(shader).read_bytes()
                self.service.apply_frame_animation(self.prepare())
                self.assertEqual(self.service.resolve(shader).read_bytes(), before)
                high = self.fixture.profiles[1]
                env = self.service.loader(
                    self.service.resolve(high["atlas"]).read_bytes()
                )
                pages = parse_atlas(
                    fixtures.text_bytes(
                        env.container[high["atlas"]["asset_path"]].deref().read()
                    )
                )
                self.assertFalse(pages[0]["pma"])

    def test_effect_shader_unknown_or_changed_blending_rejected(self):
        shader = self.effect_shader()
        original = self.fixture.payloads[shader["path_id"]]
        for mode in ("unknown", "blend", "dynamic", "no_pass"):
            tree = json.loads(original)
            parsed = tree["m_ParsedForm"]
            state = parsed["m_SubShaders"][0]["m_Passes"][0]["m_State"]
            if mode == "unknown":
                parsed["m_Name"] = "Unverified/Shader"
            elif mode == "blend":
                state["rtBlend0"]["srcBlend"]["val"] = 1
            elif mode == "dynamic":
                state["rtBlend0"]["srcBlend"]["name"] = "_SrcBlend"
            else:
                state["m_Name"] = "DepthOnly"
            self.fixture.tree(shader, tree)
            self.fixture.write()
            with self.assertRaises(ValueError):
                self.prepare()

    def add_prefab_variant(self, binding=None):
        low = self.fixture.profiles[0]
        prefab = self.fixture.add(
            "prefab", "sd", "Mesh", "variant_prefab", bundle="0000ffaa"
        )
        prefab["external_references"] = json.dumps(self.fixture.cabs)
        self.fixture.payloads[prefab["path_id"]] = b"unchanged variant mesh"
        renderer = self.fixture.add(
            "other",
            "sd",
            "MonoBehaviour",
            "variant_renderer",
            bundle=prefab["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            renderer,
            "SkeletonAnimation",
            "Spine.Unity",
            {
                "skeletonDataAsset": self.fixture.pointer(
                    renderer, binding or low["skeleton_data"]
                ),
                "initialSkinName": "",
            },
        )
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        return prefab, renderer

    def test_agreeing_prefab_variants_preserved_for_both_quality_imports(self):
        prefab, _ = self.add_prefab_variant()
        paths = [
            self.service.resolve(prefab),
            self.service.resolve(self.fixture.profiles[0]["prefab"]),
        ]
        before = {p: p.read_bytes() for p in paths}
        for lower in (False, True):
            plan = self.service.prepare_frame_animation(
                self.fixture.rows,
                self.fixture.source,
                self.options,
                lower_quality=lower,
            )
            self.service.apply_frame_animation(plan)
            self.assertEqual(before, {p: p.read_bytes() for p in paths})

    def test_multi_binding_prefab_variants_replace_every_effective_profile(self):
        self.add_prefab_variant(self.fixture.profiles[1]["skeleton_data"])
        high = self.prepare()
        self.assertEqual(high["selected_qualities"], ["highend_hd"])
        self.assertTrue(high["quality_warning"])
        low = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.assertEqual(low["selected_qualities"], ["highend_hd", "sd"])
        self.assertTrue(low["quality_warning"])
        self.service.apply_frame_animation(low)
        for profile in self.fixture.profiles:
            project = self.decoded_project(profile)
            self.assertIn(
                "floo_frames_" + profile["skeleton_json"]["quality"],
                project["flooQualityFrames"],
            )

    def test_variant_binding_outside_verified_skeletons_rejected(self):
        self.add_prefab_variant(self.fixture.reference)
        with self.assertRaisesRegex(ValueError, "outside this card"):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_variant_custom_materials_use_their_own_renderer(self):
        prefab, renderer = self.add_prefab_variant()
        custom = self.fixture.add(
            "other",
            "sd",
            "MonoBehaviour",
            "variant_custom",
            bundle=prefab["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            custom,
            "SkeletonRendererCustomMaterials",
            "Spine.Unity",
            {
                "skeletonRenderer": self.fixture.pointer(custom, renderer),
                "customSlotMaterials": [
                    {
                        "slotName": "slot",
                        "material": self.fixture.pointer(
                            custom, self.fixture.profiles[0]["materials"][0]
                        ),
                    }
                ],
            },
        )
        self.fixture.write()
        before = self.service.resolve(prefab).read_bytes()
        self.service.apply_frame_animation(self.prepare())
        self.assertEqual(self.service.resolve(prefab).read_bytes(), before)
        tree = json.loads(self.fixture.payloads[custom["path_id"]])
        other = next(
            row
            for row in self.fixture.hidden
            if row["asset_name"] == "actual_renderer" and row["quality"] == "sd"
        )
        tree["skeletonRenderer"] = self.fixture.pointer(custom, other)
        self.fixture.tree(custom, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "Playback pointer"):
            self.prepare()

    def test_preview_defers_atlas_allocation_and_apply_releases_each_page(self):
        from unity.summon_frames import AtlasSheet

        with patch.object(
            AtlasSheet, "render", side_effect=AssertionError("preview allocation")
        ):
            plan = self.prepare()
        original = AtlasSheet.render
        rendered = []

        def render(sheet):
            if rendered:
                with self.assertRaises(ValueError):
                    rendered[-1].getpixel((0, 0))
            image = original(sheet)
            rendered.append(image)
            return image

        with patch.object(AtlasSheet, "render", render):
            self.service.apply_frame_animation(plan)
        self.assertEqual(len(rendered), 2)
        for image in rendered:
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))

    def test_lazy_page_released_on_encoder_failure_without_game_writes(self):
        from unity.summon_frames import AtlasSheet

        plan = self.prepare()
        original_loader = self.service.loader
        rendered = []
        original_render = AtlasSheet.render

        def render(sheet):
            image = original_render(sheet)
            rendered.append(image)
            return image

        def load(payload):
            env = original_loader(payload)
            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    obj.asset.set_image = lambda *a, **k: (_ for _ in ()).throw(
                        ValueError("encoder failed")
                    )
            return env

        self.service.loader = load
        before = {p: p.read_bytes() for p in self.fixture.originals}
        with (
            patch.object(AtlasSheet, "render", render),
            self.assertRaisesRegex(ValueError, "encoder failed"),
        ):
            self.service.apply_frame_animation(plan)
        self.assertEqual(len(rendered), 1)
        with self.assertRaises(ValueError):
            rendered[0].getpixel((0, 0))
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def add_custom_materials(self):
        profile = self.fixture.profiles[1]
        renderer = next(
            row
            for row in self.fixture.hidden
            if row["asset_name"] == "actual_renderer" and row["quality"] == "highend_hd"
        )
        custom = self.fixture.add(
            "other",
            "highend_hd",
            "MonoBehaviour",
            "custom_materials",
            bundle=profile["prefab"]["bundle"],
            hidden=True,
        )
        self.fixture.mono(
            custom,
            "SkeletonRendererCustomMaterials",
            "Spine.Unity",
            {
                "m_Enabled": 1,
                "skeletonRenderer": self.fixture.pointer(custom, renderer),
                "customSlotMaterials": [
                    {
                        "overrideDisabled": 0,
                        "slotName": "slot",
                        "material": self.fixture.pointer(
                            custom, profile["materials"][0]
                        ),
                    }
                ],
                "customMaterialOverrides": [
                    {
                        "overrideDisabled": 1,
                        "originalMaterial": self.fixture.pointer(
                            custom, profile["materials"][0]
                        ),
                        "replacementMaterial": {"m_FileID": 0, "m_PathID": 0},
                    }
                ],
            },
        )
        self.fixture.write()
        return custom

    def add_effect_track(self):
        bundle = self.fixture.timeline["bundle"]
        clip = self.fixture.add(
            "other", None, "AnimationClip", "effect_clip", bundle=bundle, hidden=True
        )
        self.fixture.tree(
            clip,
            {
                "m_Name": "material effect",
                "m_ClipBindingConstant": {
                    "genericBindings": [
                        {
                            "typeID": 23,
                            "customType": 22,
                            "script": {"m_FileID": 0, "m_PathID": 0},
                            "isPPtrCurve": 0,
                            "isSerializeReferenceCurve": 0,
                        }
                    ],
                    "pptrCurveMapping": [],
                },
            },
        )
        asset = self.fixture.add(
            "other", None, "MonoBehaviour", "effect_asset", bundle=bundle, hidden=True
        )
        self.fixture.mono(
            asset,
            "AnimationPlayableAsset",
            "UnityEngine.Timeline",
            {
                "m_Clip": self.fixture.pointer(asset, clip),
            },
        )
        track = self.fixture.add(
            "other", None, "MonoBehaviour", "effect_track", bundle=bundle, hidden=True
        )
        self.fixture.mono(
            track,
            "AnimationTrack",
            "UnityEngine.Timeline",
            {
                "m_Children": [],
                "m_Clips": [{"m_Asset": self.fixture.pointer(track, asset)}],
            },
        )
        root = json.loads(self.fixture.payloads[self.fixture.timeline["path_id"]])
        root["m_Tracks"].append(self.fixture.pointer(self.fixture.timeline, track))
        self.fixture.tree(self.fixture.timeline, root)
        self.fixture.write()
        return clip

    def test_custom_slot_materials_and_effect_tracks_preserved_apply_restore(self):
        self.add_custom_materials()
        self.add_effect_track()
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.prepare()
        result = self.service.apply_frame_animation(plan)
        for row in [
            self.fixture.timeline,
            self.fixture.profiles[1]["prefab"],
            *self.fixture.profiles[1]["materials"],
        ]:
            path = self.service.resolve(row)
            self.assertEqual(path.read_bytes(), before[path])
        self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_timeline_reference_missing_from_metadata_is_resolved_by_pointer(self):
        self.add_animations(active="animation2")
        self.fixture.rows.remove(self.fixture.reference)
        self.fixture.hidden.append(self.fixture.reference)
        self.service.rows = [dict(row) for row in self.fixture.rows]
        self.assertEqual(self.prepare()["animation_name"], "animation2")

    def test_additional_reference_does_not_override_timeline_selected_animation(self):
        self.add_animations(active="summon")
        extra = self.fixture.add(
            "animation",
            None,
            "MonoBehaviour",
            "aux_ref",
            bundle=self.fixture.reference["bundle"],
        )
        extra["external_references"] = self.fixture.reference["external_references"]
        self.fixture.mono(
            extra,
            "AnimationReferenceAsset",
            "Spine.Unity",
            {
                "skeletonDataAsset": self.fixture.pointer(
                    extra, self.fixture.profiles[0]["skeleton_data"]
                ),
                "animationName": "auxiliary",
            },
        )
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        self.assertEqual(self.prepare()["animation_name"], "summon")

    def test_custom_slot_overrides_reject_wrong_renderer_slot_material_or_texture(self):
        custom = self.add_custom_materials()
        original = self.fixture.payloads[custom["path_id"]]
        for field, value in (
            ("skeletonRenderer", self.fixture.pointer(custom, self.fixture.reference)),
            ("slotName", "missing"),
            (
                "material",
                self.fixture.pointer(custom, self.fixture.profiles[1]["skeleton_data"]),
            ),
        ):
            with self.subTest(field=field, value=value):
                tree = json.loads(original)
                if field == "skeletonRenderer":
                    tree[field] = value
                else:
                    tree["customSlotMaterials"][0][field] = value
                self.fixture.tree(custom, tree)
                self.fixture.write()
                with self.assertRaises(ValueError):
                    self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_active_whole_skeleton_material_override_rejected(self):
        custom = self.add_custom_materials()
        tree = json.loads(self.fixture.payloads[custom["path_id"]])
        tree["customMaterialOverrides"][0]["overrideDisabled"] = 0
        self.fixture.tree(custom, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "whole-skeleton"):
            self.prepare()

    def test_auxiliary_effect_clip_pointer_script_event_and_transform_bindings_rejected(
        self,
    ):
        clip = self.add_effect_track()
        original = self.fixture.payloads[clip["path_id"]]
        for mode in ("pointer", "script", "transform", "event"):
            with self.subTest(mode=mode):
                tree = json.loads(original)
                binding = tree["m_ClipBindingConstant"]["genericBindings"][0]
                if mode == "pointer":
                    binding["isPPtrCurve"] = 1
                elif mode == "script":
                    binding["script"]["m_PathID"] = 123
                elif mode == "transform":
                    binding["typeID"] = 4
                else:
                    tree["m_Events"] = [{"functionName": "unsafe"}]
                self.fixture.tree(clip, tree)
                self.fixture.write()
                with self.assertRaisesRegex(ValueError, "Auxiliary animation"):
                    self.prepare()

    def shared_renderer(self, target=None):
        renderer = next(
            row
            for row in self.fixture.hidden
            if row["role"] == "other"
            and row["asset_name"] == "actual_renderer"
            and row["quality"] == "highend_hd"
        )
        tree = json.loads(self.fixture.payloads[renderer["path_id"]])
        tree["skeletonDataAsset"] = self.fixture.pointer(
            renderer, target or self.fixture.profiles[0]["skeleton_data"]
        )
        self.fixture.tree(renderer, tree)
        clip = json.loads(self.fixture.payloads[self.fixture.clip["path_id"]])
        clip["template"].update(customDuration=1, useBlendDuration=1, mixDuration=0.1)
        self.fixture.tree(self.fixture.clip, clip)
        self.fixture.write()

    def test_shared_renderer_follows_actual_binding_preserves_dormant_hd_and_mix(self):
        self.shared_renderer()
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.prepare()
        self.assertEqual(plan["selected_qualities"], ["sd"])
        self.assertEqual(plan["quality_bindings"], {"sd": "sd", "highend_hd": "sd"})
        self.assertEqual(plan["quality_label"], "Shared quality")
        self.assertIn("both quality modes", plan["quality_warning"])
        result = self.service.apply_frame_animation(plan)
        hd = self.fixture.profiles[1]
        for row in [
            hd["skeleton_json"],
            hd["atlas"],
            *hd["textures"],
            self.fixture.timeline,
            hd["prefab"],
        ]:
            path = self.service.resolve(row)
            self.assertEqual(path.read_bytes(), before[path])
        project = self.decoded_project(self.fixture.profiles[0])
        self.assertIn("floo_frames_sd", project["animations"]["animation"]["slots"])
        self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_shared_renderer_lower_selection_reports_both_modes(self):
        self.shared_renderer()
        plan = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.assertEqual(plan["selected_qualities"], ["sd"])
        self.assertIn("both quality modes", plan["quality_warning"])

    def test_renderer_binding_outside_verified_profiles_is_rejected(self):
        self.shared_renderer(self.fixture.profiles[0]["atlas_asset"])
        with self.assertRaisesRegex(ValueError, "outside this card"):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_looping_and_open_ended_clips_still_rejected(self):
        for flag in ("loop", "dontEndWithClip"):
            with self.subTest(flag=flag):
                original = self.fixture.payloads[self.fixture.clip["path_id"]]
                tree = json.loads(original)
                tree["template"][flag] = 1
                self.fixture.tree(self.fixture.clip, tree)
                self.fixture.write()
                with self.assertRaisesRegex(ValueError, "Looping or open-ended"):
                    self.prepare()
                self.fixture.payloads[self.fixture.clip["path_id"]] = original
                self.fixture.write()

    def test_preview_no_writes_all_profiles_apply_unchanged_wrappers_restore(self):
        plan = self.prepare()
        self.assertIn("High quality", plan["summary"])
        self.assertFalse((self.fixture.root / "backups").exists())
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )
        result = self.service.apply_frame_animation(plan)
        changed = [
            p
            for p, original in self.fixture.originals.items()
            if p.read_bytes() != original
        ]
        self.assertEqual(
            len(changed), 5
        )  # two compatibility JSONs, HD atlas and two textures
        for p, original in self.fixture.originals.items():
            if p not in changed:
                self.assertEqual(p.read_bytes(), original)
        env = self.service.loader(
            self.service.resolve(self.fixture.unrelated).read_bytes()
        )
        obj = env.container[self.fixture.unrelated["asset_path"]].deref()
        self.assertEqual(
            fixtures.text_bytes(obj.read()), b"unchanged arbitrary bytes\xff"
        )
        self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )

    def test_stale_dependency_and_running_game_refuse_before_writes(self):
        plan = self.prepare()
        path = self.service.resolve(self.fixture.timeline)
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            self.service.apply_frame_animation(plan)
        self.assertFalse((self.fixture.root / "backups").exists())
        path.write_bytes(original)
        self.service.running = lambda: True
        with self.assertRaises(RuntimeError):
            self.service.apply_frame_animation(plan)

    def test_unsupported_modifier_and_pointer_fail_closed(self):
        data = self.fixture.profiles[0]["skeleton_data"]
        tree = json.loads(self.fixture.payloads[data["path_id"]])
        tree["skeletonDataModifiers"] = [{"m_FileID": 0, "m_PathID": 1}]
        self.fixture.tree(data, tree)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "modifiers"):
            self.prepare()
        tree["skeletonDataModifiers"] = []
        tree["skeletonJSON"]["m_PathID"] = 99999
        self.fixture.tree(data, tree)
        self.fixture.write()
        with self.assertRaises(ValueError):
            self.prepare()

    def test_failed_second_commit_rolls_back_every_bundle(self):
        plan = self.prepare()
        import services.summon_animation_service as module

        original_replace = module.os.replace
        calls = []

        def replace(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError("injected replacement failure")
            return original_replace(source, destination)

        with (
            patch.object(module.os, "replace", side_effect=replace),
            self.assertRaises(OSError),
        ):
            self.service.apply_frame_animation(plan)
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )

    def add_animations(self, active="summon"):
        for profile in self.fixture.profiles:
            row = profile["skeleton_json"]
            project = json.loads(self.fixture.payloads[row["path_id"]])
            original = project["animations"]["animation"]
            project["events"] = {"aux": {"int": 7}}
            project["animations"] = {
                "auxiliary": {"events": [{"time": 2, "name": "aux", "int": 9}]},
                "empty": {},
                active: original,
            }
            row["animation_names"] = json.dumps(sorted(project["animations"]))
            self.fixture.tree(row, project)
        tree = json.loads(self.fixture.payloads[self.fixture.reference["path_id"]])
        tree["animationName"] = active
        self.fixture.tree(self.fixture.reference, tree)
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]

    def test_multi_animation_uses_reference_not_first_and_preserves_names_events(self):
        self.add_animations()
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.prepare()
        self.assertEqual(plan["animation_name"], "summon")
        result = self.service.apply_frame_animation(plan)
        for profile in self.fixture.profiles:
            row = profile["skeleton_json"]
            env = self.service.loader(self.service.resolve(row).read_bytes())
            project = json.loads(
                fixtures.text_bytes(env.container[row["asset_path"]].deref().read())
            )
            self.assertEqual(
                set(project["animations"]), {"auxiliary", "empty", "summon"}
            )

            def keys(name):
                return project["animations"][name]["slots"]["floo_frames_highend_hd"][
                    "attachment"
                ]

            self.assertEqual(keys("summon")[-1]["time"], 1)
            self.assertEqual(keys("auxiliary")[-1]["time"], 2)
            self.assertEqual(
                keys("empty"), [{"time": 0, "name": "floo_frames_highend_hd_0000"}]
            )
            self.assertEqual(
                project["animations"]["auxiliary"]["events"],
                [{"time": 2, "name": "aux", "int": 9}],
            )
            self.assertEqual(project["events"], {"aux": {"int": 7}})
        self.service.restore_component_set(manifests=result["manifests"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_missing_referenced_animation_reports_profile_and_available_names(self):
        self.add_animations()
        tree = json.loads(self.fixture.payloads[self.fixture.reference["path_id"]])
        tree["animationName"] = "missing"
        self.fixture.tree(self.fixture.reference, tree)
        self.fixture.write()
        with self.assertRaisesRegex(
            ValueError,
            "Timeline animation 'missing'.*sd.*Available animations: auxiliary, empty, summon",
        ):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_unsupported_version_reports_actual_version_separately(self):
        for profile in self.fixture.profiles:
            row = profile["skeleton_json"]
            project = json.loads(self.fixture.payloads[row["path_id"]])
            project["skeleton"]["spine"] = "4.1.24"
            row["spine_version"] = "4.1.24"
            self.fixture.tree(row, project)
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        with self.assertRaisesRegex(
            ValueError, "Unsupported Spine version 4.1.24 in sd"
        ):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_mismatched_additional_profile_names_are_refused(self):
        self.add_animations()
        row = self.fixture.profiles[1]["skeleton_json"]
        project = json.loads(self.fixture.payloads[row["path_id"]])
        del project["animations"]["empty"]
        row["animation_names"] = json.dumps(sorted(project["animations"]))
        self.fixture.tree(row, project)
        self.fixture.write()
        self.service.rows = [dict(row) for row in self.fixture.rows]
        with self.assertRaisesRegex(
            ValueError, "Profiles use different animation names"
        ):
            self.prepare()

    def decoded_project(self, profile):
        row = profile["skeleton_json"]
        env = self.service.loader(self.service.resolve(row).read_bytes())
        return json.loads(
            fixtures.text_bytes(env.container[row["asset_path"]].deref().read())
        )

    def assert_image_files_unchanged(self, profile, before):
        for row in [profile["atlas"], *profile["textures"]]:
            path = self.service.resolve(row)
            self.assertEqual(path.read_bytes(), before[path])

    def test_high_quality_only_keeps_low_images_and_original_motion(self):
        low, high = self.fixture.profiles
        original = json.loads(self.fixture.payloads[low["skeleton_json"]["path_id"]])
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.prepare()
        self.assertFalse(plan["lower_quality"])
        self.service.apply_frame_animation(plan)
        self.assert_image_files_unchanged(low, before)
        low_project, high_project = self.decoded_project(low), self.decoded_project(
            high
        )
        for key in ("bones", "slots"):
            self.assertEqual(low_project[key][: len(original[key])], original[key])
            self.assertEqual(
                [(v["name"]) for v in low_project[key]],
                [(v["name"]) for v in high_project[key]],
            )
        self.assertEqual(
            low_project["animations"]["animation"]["bones"],
            original["animations"]["animation"]["bones"],
        )
        self.assertEqual(
            low_project["skins"][0]["attachments"]["slot"],
            original["skins"][0]["attachments"]["slot"],
        )
        name = "floo_frames_highend_hd"
        self.assertTrue(
            all(
                a["type"] == "point"
                for a in low_project["skins"][0]["attachments"][name].values()
            )
        )
        self.assertTrue(
            all(
                a["type"] == "region"
                for a in high_project["skins"][0]["attachments"][name].values()
            )
        )
        self.assertEqual(
            low_project["animations"]["animation"]["slots"][name],
            high_project["animations"]["animation"]["slots"][name],
        )
        env = self.service.loader(self.service.resolve(high["atlas"]).read_bytes())
        pages = parse_atlas(
            fixtures.text_bytes(
                env.container[high["atlas"]["asset_path"]].deref().read()
            )
        )
        for page, texture in zip(pages, high["textures"]):
            env = self.service.loader(self.service.resolve(texture).read_bytes())
            image = env.container[texture["asset_path"]].deref().read().image
            old_region = next(
                r for r in page["regions"] if r["name"].startswith("region")
            )
            self.assertEqual(image.getpixel(old_region["rectangle"][:2]), (0, 0, 0, 0))

    def test_lower_quality_only_keeps_high_images(self):
        before = {p: p.read_bytes() for p in self.fixture.originals}
        plan = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.assertTrue(plan["lower_quality"])
        self.service.apply_frame_animation(plan)
        self.assert_image_files_unchanged(self.fixture.profiles[1], before)
        low = self.decoded_project(self.fixture.profiles[0])
        high = self.decoded_project(self.fixture.profiles[1])
        name = "floo_frames_sd"
        self.assertTrue(
            all(
                a["type"] == "region"
                for a in low["skins"][0]["attachments"][name].values()
            )
        )
        self.assertTrue(
            all(
                a["type"] == "point"
                for a in high["skins"][0]["attachments"][name].values()
            )
        )

    def test_alternating_quality_edits_preserve_other_replacement_and_restore(self):
        self.service.apply_frame_animation(self.prepare())
        high_before = {
            self.service.resolve(r): self.service.resolve(r).read_bytes()
            for r in [
                self.fixture.profiles[1]["atlas"],
                *self.fixture.profiles[1]["textures"],
            ]
        }
        old_high = self.decoded_project(self.fixture.profiles[1])
        low_plan = self.service.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        self.service.apply_frame_animation(low_plan)
        self.assert_image_files_unchanged(self.fixture.profiles[1], high_before)
        new_high = self.decoded_project(self.fixture.profiles[1])
        self.assertEqual(
            new_high["skins"][0]["attachments"]["floo_frames_highend_hd"],
            old_high["skins"][0]["attachments"]["floo_frames_highend_hd"],
        )
        self.assertEqual(
            new_high["animations"]["animation"]["slots"]["floo_frames_highend_hd"],
            old_high["animations"]["animation"]["slots"]["floo_frames_highend_hd"],
        )
        low_before = {
            self.service.resolve(r): self.service.resolve(r).read_bytes()
            for r in [
                self.fixture.profiles[0]["atlas"],
                *self.fixture.profiles[0]["textures"],
            ]
        }
        self.service.apply_frame_animation(self.prepare())
        self.assert_image_files_unchanged(self.fixture.profiles[0], low_before)
        entries = self.service.backup_inventory()
        self.service.restore_component_set(manifests=[e["path"] for e in entries])
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )

    def test_incompatible_profile_indices_rejected_before_writes(self):
        row = self.fixture.profiles[1]["skeleton_json"]
        project = json.loads(self.fixture.payloads[row["path_id"]])
        project["bones"].append({"name": "extra", "parent": "root"})
        self.fixture.tree(row, project)
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, "incompatible playback structures"):
            self.prepare()
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_legacy_local_only_originals_reused_after_streaming_root_detection(self):
        first = self.service.apply_frame_animation(self.prepare())
        old_paths = set(first["manifests"])
        new = SummonAnimationService(
            Installation(
                "global",
                self.fixture.installation.local_root,
                self.fixture.root / "streaming",
            ),
            self.fixture.rows,
            loader=self.fixture.load,
            running=lambda: False,
            backup_root=self.fixture.root / "backups",
        )
        self.assertEqual({e["path"] for e in new.backup_inventory()}, old_paths)
        low_plan = new.prepare_frame_animation(
            self.fixture.rows, self.fixture.source, self.options, lower_quality=True
        )
        new.apply_frame_animation(low_plan)
        all_paths = [e["path"] for e in new.backup_inventory()]
        self.assertTrue(old_paths.issubset(all_paths))
        new.restore_component_set(manifests=all_paths)
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )

    def stream_loader(self, path="archive:/CAB/internal.resS", corrupt=False):
        def load(payload):
            env = GraphFixture.load(payload)
            textures = [o for o in env.objects if o.type.name == "Texture2D"]
            resource = b"resource"
            if (
                corrupt
                and textures
                and textures[0].asset.image.getpixel((0, 0)) != (255, 80, 0, 128)
            ):
                resource = b"corrupted resource"
            env.file.files = {"internal.resS": SimpleNamespace(bytes=resource)}
            for obj in textures:
                obj.asset.m_StreamData = SimpleNamespace(path=path, offset=0, size=8)
                original_set = obj.set_image

                def set_image(
                    image,
                    target_format,
                    mipmap_count,
                    obj=obj,
                    original_set=original_set,
                ):
                    original_set(image, target_format, mipmap_count)
                    obj.asset.m_StreamData.path = ""

                obj.asset.set_image = set_image
            return env

        return load

    def test_internal_streams_supported_external_sidecars_rejected(self):
        self.service.loader = self.stream_loader()
        plan = self.prepare()
        self.service.apply_frame_animation(plan)
        # A fresh fixture isolates the external-sidecar rejection.
        fixture = GraphFixture(self.fixture.root / "external")
        fixture.service.loader = self.stream_loader(path="C:/outside/internal.resS")
        plan = fixture.service.prepare_frame_animation(
            fixture.rows, fixture.source, self.options
        )
        with self.assertRaisesRegex(ValueError, "sidecars"):
            fixture.service.apply_frame_animation(plan)
        self.assertFalse((fixture.root / "backups").exists())

    def test_internal_resources_must_remain_identical(self):
        self.service.loader = self.stream_loader(corrupt=True)
        plan = self.prepare()
        with self.assertRaisesRegex(ValueError, "resource"):
            self.service.apply_frame_animation(plan)
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )
        self.assertFalse((self.fixture.root / "backups").exists())

    def test_unknown_compression_is_refused(self):
        self.service.packer = "lz4hc"
        plan = self.prepare()
        with self.assertRaisesRegex(ValueError, "compression"):
            self.service.apply_frame_animation(plan)
        self.assertFalse((self.fixture.root / "backups").exists())


if __name__ == "__main__":
    unittest.main()
