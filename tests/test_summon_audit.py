"""Synthetic regression checks for the read-only full-catalog audit."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_summon_frames import GraphFixture
from services.summon_animation_audit import (
    ReadOnlySummonService,
    audit_card,
    choose_cards,
    synthetic_sources,
)
from services.summon_animation_service import SummonAnimationService
from unity.summon_frames import FrameOptions
from tools.audit_summon_animations import launch_worker, write_report


class SummonAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = GraphFixture(self.temp.name)
        self.service = ReadOnlySummonService(
            self.fixture.installation,
            self.fixture.rows,
            loader=self.fixture.load,
            backup_root=Path(self.temp.name) / "audit-backups",
        )
        self.card = choose_cards(self.fixture.rows, "global", "tcg")[0]
        source = Path(self.temp.name) / "audit-source"
        source.mkdir()
        self.sources = synthetic_sources(source)
        self.options = FrameOptions(edge=32, fps=10, png_fps=10)

    def test_full_audit_checks_both_formats_qualities_without_writes_or_backups(self):
        with (
            patch.object(
                SummonAnimationService,
                "_commit",
                side_effect=AssertionError("disk commit"),
            ),
            patch.object(
                SummonAnimationService,
                "backup_component_set",
                side_effect=AssertionError("disk backup"),
            ),
        ):
            result = audit_card(self.service, self.card, self.sources, self.options)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            {(case["quality"], case["format"]) for case in result["cases"]},
            {("high", "png"), ("high", "gif"), ("lower", "png"), ("lower", "gif")},
        )
        self.assertTrue(
            all(case["stage"] == "serialization" for case in result["cases"])
        )
        self.assertTrue(
            any(
                case.get("serialization_reused_from") == "png"
                for case in result["cases"]
            )
        )
        self.assertFalse(self.service.backups.root.exists())
        self.assertEqual(
            self.fixture.originals, {p: p.read_bytes() for p in self.fixture.originals}
        )

    def test_preview_mode_never_serializes(self):
        with patch.object(
            self.service,
            "apply_frame_animation",
            side_effect=AssertionError("serialization"),
        ):
            result = audit_card(
                self.service, self.card, self.sources, self.options, preview_only=True
            )
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(case["stage"] == "preview" for case in result["cases"]))

    def test_missing_download_is_distinct_from_import_failure(self):
        self.service.resolve(self.fixture.profiles[0]["atlas"]).unlink()
        with patch.object(self.service, "prepare_frame_animation") as prepare:
            result = audit_card(self.service, self.card, self.sources, self.options)
        prepare.assert_not_called()
        self.assertEqual(result["status"], "missing_assets")
        self.assertEqual(len(result["missing_bundles"]), 1)

    def test_graph_failure_reports_all_cases_without_repeating_previews(self):
        clip = self.fixture.clip
        tree = json.loads(self.fixture.payloads[clip["path_id"]])
        tree["template"]["loop"] = 1
        self.fixture.tree(clip, tree)
        self.fixture.write()
        with patch.object(self.service, "prepare_frame_animation") as prepare:
            result = audit_card(self.service, self.card, self.sources, self.options)
        prepare.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["cases"]), 4)
        self.assertTrue(all(case["stage"] == "graph" for case in result["cases"]))

    def test_one_failure_does_not_hide_other_formats_or_qualities(self):
        original = self.service.prepare_frame_animation

        def prepare(rows, source, options, lower_quality=False):
            if source == self.sources["png"] and not lower_quality:
                raise ValueError("synthetic PNG failure")
            return original(rows, source, options, lower_quality=lower_quality)

        with patch.object(self.service, "prepare_frame_animation", side_effect=prepare):
            result = audit_card(
                self.service, self.card, self.sources, self.options, preview_only=True
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(sum(case["status"] == "passed" for case in result["cases"]), 3)

    def test_regions_follow_gui_preference_then_common_fallback(self):
        rows = self.fixture.rows
        common = [dict(row, asset_region="common") for row in rows]
        ocg = [dict(row, game_region="ocg", asset_region="ocg") for row in rows]
        self.assertEqual(
            choose_cards(rows + common + ocg, "global", "tcg")[0]["asset_region"], "tcg"
        )
        self.assertEqual(
            choose_cards(common + ocg, "global", "tcg")[0]["asset_region"], "common"
        )

    def test_worker_timeout_and_native_crash_are_reported(self):
        import subprocess
        from types import SimpleNamespace

        with patch(
            "tools.audit_summon_animations.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 5),
        ):
            result = launch_worker("unused", 0, self.card, 5)
        self.assertEqual(result["stage"], "worker")
        with patch(
            "tools.audit_summon_animations.subprocess.run",
            return_value=SimpleNamespace(stdout="", returncode=123),
        ):
            result = launch_worker("unused", 0, self.card, 5)
        self.assertEqual(result["status"], "failed")
        self.assertIn("123", result["error"])

    def test_report_destination_cannot_overwrite_assets_or_database(self):
        from tools.audit_summon_animations import validate_report_path

        config = {
            "local_root": str(self.fixture.installation.local_root),
            "streaming_root": None,
        }
        database = Path(self.temp.name) / "metadata.json"
        for path in (self.fixture.installation.local_root / "report.json", database):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_report_path(path, config, database)
        validate_report_path(
            Path(self.temp.name) / "valid-report.json", config, database
        )

    def test_resume_requires_unchanged_dependency_bytes(self):
        import hashlib
        from tools.audit_summon_animations import can_reuse

        row = self.fixture.profiles[0]["skeleton_json"]
        path = self.service.resolve(row)
        config = {
            "game_region": "global",
            "local_root": str(self.fixture.installation.local_root),
            "streaming_root": None,
        }
        result = {
            "status": "passed",
            "asset_checksums": [
                {
                    "source": "local",
                    "bundle": row["bundle"],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            ],
        }
        self.assertTrue(can_reuse(result, config))
        path.write_bytes(path.read_bytes() + b"changed")
        self.assertFalse(can_reuse(result, config))
        self.assertFalse(can_reuse({"status": "failed"}, config))

    def test_windows_progress_logs_support_unicode_card_names(self):
        import os
        import subprocess
        import sys

        code = (
            "import sys; from tools.audit_summon_animations import configure_output; "
            "configure_output(); name='Evil\\u2605Twin Ki-sikil'; "
            "print(name, flush=True); print(name, file=sys.stderr, flush=True)"
        )
        # Replace the literal escape in the command with Python's Unicode escape.
        code = code.replace("\\\\u2605", "\\u2605")
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ, PYTHONIOENCODING="cp1252"),
            capture_output=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(result.stdout.decode("utf-8").strip(), "Evil★Twin Ki-sikil")
        self.assertEqual(result.stderr.decode("utf-8").strip(), "Evil★Twin Ki-sikil")

    def test_importer_snapshot_keeps_revision_when_source_changes(self):
        from tools.audit_summon_animations import (
            IMPORTER_FILES,
            importer_fingerprint,
            make_importer_snapshot,
        )

        source = Path(self.temp.name) / "source"
        for name in IMPORTER_FILES:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original " + name, encoding="utf-8")
        revision = importer_fingerprint(source)
        snapshot = make_importer_snapshot(Path(self.temp.name) / "run", source)
        self.assertEqual(importer_fingerprint(snapshot), revision)
        (source / IMPORTER_FILES[0]).write_text("changed", encoding="utf-8")
        self.assertNotEqual(importer_fingerprint(source), revision)
        self.assertEqual(importer_fingerprint(snapshot), revision)

    def test_progress_reports_export_json_and_csv(self):
        path = Path(self.temp.name) / "report.json"
        result = {
            key: self.card[key] for key in ("card_id", "display_name", "asset_region")
        }
        result.update(
            status="failed",
            cases=[
                {
                    "format": "gif",
                    "quality": "high",
                    "status": "failed",
                    "stage": "preview",
                    "error": "test error",
                }
            ],
        )
        write_report(path, {"complete": False, "cards": [result]})
        self.assertFalse(json.loads(path.read_text())["complete"])
        self.assertIn(
            "test error", path.with_suffix(".csv").read_text(encoding="utf-8-sig")
        )
        self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
