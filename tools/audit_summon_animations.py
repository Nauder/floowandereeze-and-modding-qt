"""Audit every configured summon animation without writing game assets.

Run: python tools/audit_summon_animations.py --report build/summon-audit/report.json
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_configuration(database):
    """Read the GUI's metadata and installation settings without ORM migrations."""
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        config = connection.execute("SELECT * FROM app_config LIMIT 1").fetchone()
        if config is None or not config["game_path"]:
            raise ValueError("Set your game path in Configuration first.")
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(summon_animation_asset)")
        ]
        if not columns:
            raise ValueError("Refresh summon metadata in Configuration first.")
        from unity.summon_metadata import COLUMNS

        rows = [
            {key: row[key] for key in COLUMNS}
            for row in connection.execute("SELECT * FROM summon_animation_asset")
        ]
    region = (config["asset_region"] or "tcg").lower()
    if region not in {"tcg", "ocg"}:
        raise ValueError("Choose TCG/Global or OCG in Configuration.")
    player = Path(config["game_path"]).resolve()
    streaming = (
        player.parent.parent / "masterduel_Data" / "StreamingAssets" / "AssetBundle"
    )
    return {
        "game_region": "ocg" if region == "ocg" else "global",
        "asset_region": region,
        "local_root": str(player / "0000"),
        "streaming_root": str(streaming) if streaming.is_dir() else None,
        "packer": config["packer"] or "lz4",
        "rows": rows,
    }


def validate_report_path(path, config, database):
    """Reports must never overwrite installed assets, backups or the metadata database."""
    path = Path(path)
    roots = [Path(config["local_root"]).resolve(), ROOT / "backups"]
    if config["streaming_root"]:
        roots.append(Path(config["streaming_root"]).resolve())
    for candidate in (
        path,
        path.with_suffix(".csv"),
        path.with_suffix(".csv.tmp"),
        path.with_suffix(path.suffix + ".tmp"),
    ):
        resolved = candidate.resolve()
        if resolved == Path(database).resolve() or any(
            resolved == root or root in resolved.parents for root in roots
        ):
            raise ValueError(
                "Choose a report destination outside game assets, backups and the database."
            )


IMPORTER_FILES = (
    "services/summon_animation_service.py",
    "unity/summon_flipbook_graph.py",
    "unity/summon_frames.py",
    "unity/summon_spine.py",
)


def importer_fingerprint(source_root=ROOT):
    """Invalidate resume results after changing the production importer."""
    digest = hashlib.sha256()
    for name in IMPORTER_FILES:
        digest.update((Path(source_root) / name).read_bytes())
    return digest.hexdigest()


def make_importer_snapshot(folder, source_root=ROOT):
    """Freeze importer source for this run; batch fixes cannot change its workers."""
    destination = Path(folder) / "importer"
    for name in IMPORTER_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((Path(source_root) / name).read_bytes())
    return destination


def install_importer_snapshot(folder):
    """Load frozen modules before the read-only service imports its base class."""
    for name in (
        "unity.summon_spine",
        "unity.summon_frames",
        "services.summon_animation_service",
        "unity.summon_flipbook_graph",
    ):
        parent, _, leaf = name.rpartition(".")
        package = importlib.import_module(parent)
        path = Path(folder) / (name.replace(".", "/") + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        setattr(package, leaf, module)


def write_report(path, report):
    """Save progress atomically and export a flat per-case CSV beside the JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
    csv_temporary = path.with_suffix(".csv.tmp")
    with csv_temporary.open("w", newline="", encoding="utf-8-sig") as output:
        columns = [
            "card_id",
            "display_name",
            "asset_region",
            "quality",
            "format",
            "status",
            "stage",
            "error",
        ]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for card in report["cards"]:
            for case in card.get("cases") or [{}]:
                writer.writerow(
                    {key: case.get(key, card.get(key, "")) for key in columns}
                )

    try:
        csv_temporary.replace(path.with_suffix(".csv"))
    except PermissionError:
        csv_temporary.unlink(missing_ok=True)
        print(
            "CSV report is open; JSON progress is still updated. Close CSV to refresh it.",
            flush=True,
        )


def worker(manifest, index):
    """Isolate native encoders and memory usage to one card per process."""
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    source_root = Path(data.get("snapshot_root", ROOT))
    if "snapshot_root" in data:
        install_importer_snapshot(source_root)

    from services.summon_animation_audit import (
        ReadOnlySummonService,
        audit_card,
        synthetic_sources,
    )
    from services.summon_animation_service import Installation
    from unity.summon_frames import FrameOptions

    installation = Installation(
        data["game_region"], data["local_root"], data["streaming_root"]
    )
    revision = importer_fingerprint(source_root)
    if data.get("importer_sha256", revision) != revision:
        result = {
            key: data["cards"][index][key]
            for key in ("card_id", "display_name", "asset_region")
        }
        return dict(
            result,
            status="failed",
            stage="importer_changed",
            cases=[],
            error="Importer changed after the audit started; run a fresh audit.",
        )
    service = ReadOnlySummonService(installation, data["rows"], data["packer"])
    with TemporaryDirectory(prefix="floo-summon-input-") as folder:
        result = audit_card(
            service,
            data["cards"][index],
            synthetic_sources(folder),
            FrameOptions(edge=data["edge"], fps=data["fps"]),
            preview_only=data["preview_only"],
        )
    result["importer_sha256"] = revision
    if importer_fingerprint(source_root) != revision:
        result.update(
            status="failed",
            stage="importer_changed",
            error="Importer changed during this check; run a fresh audit.",
        )
    return result


def can_reuse(result, config):
    """Resume only successful checks whose dependency bytes still match."""
    if result.get("status") != "passed" or not result.get("asset_checksums"):
        return False
    from services.summon_animation_service import Installation

    installation = Installation(
        config["game_region"], config["local_root"], config["streaming_root"]
    )
    try:
        for snapshot in result["asset_checksums"]:
            bundle = snapshot["bundle"]
            if len(bundle) != 8 or any(
                char not in "0123456789abcdefABCDEF" for char in bundle
            ):
                return False
            path = installation.path(snapshot["source"], bundle[:2] + "/" + bundle)
            if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["sha256"]:
                return False
    except (OSError, ValueError, KeyError):
        return False
    return True


def launch_worker(manifest, index, card, timeout):
    """Turn timeouts/native crashes into results and continue the rest of the audit."""
    started = time.monotonic()
    base = {key: card[key] for key in ("card_id", "display_name", "asset_region")}
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--manifest",
                str(manifest),
                "--index",
                str(index),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        lines = completed.stdout.strip().splitlines()
        result = json.loads(lines[-1]) if lines else None
        if not isinstance(result, dict) or completed.returncode:
            raise ValueError(f"Worker exited with code {completed.returncode}.")
    except subprocess.TimeoutExpired:
        result = dict(
            base,
            status="failed",
            stage="worker",
            cases=[],
            error=f"Worker exceeded {timeout} seconds.",
        )
    except (OSError, ValueError) as error:
        result = dict(base, status="failed", stage="worker", cases=[], error=str(error))
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def configure_output():
    """Keep Unicode card names safe in redirected Windows progress logs."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def main():
    """Run a full audit or a quicker preview-only compatibility scan."""
    configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "database.db")
    parser.add_argument(
        "--report", type=Path, default=ROOT / "build/summon-audit/report.json"
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Skip native encoding and bundle save/reload.",
    )
    parser.add_argument(
        "--edge", type=int, default=256, help="Frame long edge; GUI default is 256."
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--jobs", type=int, default=2, help="Concurrent isolated card processes (1–4)."
    )
    parser.add_argument(
        "--timeout", type=int, default=180, help="Seconds allowed per card."
    )
    parser.add_argument(
        "--card",
        action="append",
        help="Only these card IDs; repeat for multiple cards.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed results when inputs/options match.",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--index", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        import contextlib

        # Third-party diagnostics must not corrupt the worker JSON protocol.
        with contextlib.redirect_stdout(io.StringIO()):
            result = worker(args.manifest, args.index)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    if args.report.suffix.lower() != ".json":
        parser.error("--report must use a .json filename.")
    if not 1 <= args.jobs <= 4 or args.timeout < 1:
        parser.error("--jobs must be 1–4 and --timeout must be positive.")
    from services.summon_animation_audit import choose_cards
    from unity.summon_frames import FrameOptions

    FrameOptions(edge=args.edge, fps=args.fps).validate()
    config = load_configuration(args.database)
    validate_report_path(args.report, config, args.database)
    config["importer_sha256"] = importer_fingerprint()
    cards = choose_cards(config["rows"], config["game_region"], config["asset_region"])
    if args.card:
        cards = [card for card in cards if card["card_id"] in args.card]
    if not cards:
        parser.error("No matching summon cards found in configured metadata.")
    manifest_data = dict(
        config,
        cards=cards,
        edge=args.edge,
        fps=args.fps,
        preview_only=args.preview_only,
    )
    fingerprint = hashlib.sha256(
        json.dumps(manifest_data, sort_keys=True).encode()
    ).hexdigest()
    report = {
        "schema": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "mode": "preview" if args.preview_only else "serialization",
        "game_region": config["game_region"],
        "asset_region": config["asset_region"],
        "options": {"edge": args.edge, "fps": args.fps, "synthetic_frames": 2},
        "fingerprint": fingerprint,
        "importer_sha256": config["importer_sha256"],
        "total_cards": len(cards),
        "cards": [],
        "limitations": "Synthetic-input compatibility only; does not verify in-game visual playback or every possible source.",
    }
    if args.resume and args.report.is_file():
        previous = json.loads(args.report.read_text(encoding="utf-8"))
        if previous.get("fingerprint") != fingerprint:
            parser.error(
                "Report inputs/options/importer differ; use a new report path or omit --resume."
            )
        report["cards"] = [
            result for result in previous["cards"] if can_reuse(result, config)
        ]
    done = {(card["card_id"], card["asset_region"]) for card in report["cards"]}
    print(
        f"Auditing {len(cards)} cards; mode={report['mode']}; game files will not be written.",
        flush=True,
    )
    report["summary"] = dict(Counter(card["status"] for card in report["cards"]))
    write_report(args.report, report)
    started = time.monotonic()
    with TemporaryDirectory(prefix="floo-summon-audit-") as folder:
        snapshot = make_importer_snapshot(folder)
        if importer_fingerprint(snapshot) != config["importer_sha256"]:
            raise ValueError(
                "Importer changed while creating its snapshot; resume the audit."
            )
        manifest_data["snapshot_root"] = str(snapshot)
        manifest = Path(folder) / "manifest.json"
        manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [
                pool.submit(launch_worker, manifest, index, card, args.timeout)
                for index, card in enumerate(cards)
                if (card["card_id"], card["asset_region"]) not in done
            ]
            for future in as_completed(futures):
                result = future.result()
                report["cards"].append(result)
                report["summary"] = dict(
                    Counter(card["status"] for card in report["cards"])
                )
                write_report(args.report, report)
                errors = [
                    case["error"]
                    for case in result.get("cases", [])
                    if case.get("error")
                ]
                detail = (errors[0] if errors else result.get("error", ""))[:140]
                print(
                    f"[{len(report['cards'])}/{len(cards)}] {result['display_name']}: {result['status']} {detail}",
                    flush=True,
                )
    report["cards"].sort(
        key=lambda card: (card["display_name"].casefold(), card["card_id"])
    )
    report.update(
        complete=True,
        elapsed_seconds=round(time.monotonic() - started, 3),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    report["summary"] = dict(Counter(card["status"] for card in report["cards"]))
    write_report(args.report, report)
    print("Summary:", json.dumps(report["summary"]), flush=True)
    print("Report:", args.report, flush=True)
    return (
        1
        if report["summary"].get("failed") or report["summary"].get("missing_assets")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
