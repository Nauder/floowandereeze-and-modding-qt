"""Read-only batch probes of the real summon replacement pipeline."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from services.summon_animation_service import SummonAnimationService


class ReadOnlySummonService(SummonAnimationService):
    """Run real encoding/save/reload checks, with disk mutation hooks disabled."""

    def __init__(self, *args, **kwargs):
        kwargs["running"] = lambda: False
        super().__init__(*args, **kwargs)
        self.serialized_bundles = 0
        self.serialized_bytes = 0

    def backup_component_set(self, rows, operation=None):
        """An audit creates no game backups or manifests."""
        return []

    def _commit(self, outputs, originals):
        """Discard staged bytes after confirming installed originals are unchanged."""
        for path, original in originals.items():
            if path.read_bytes() != original:
                raise ValueError("Installed assets changed during the audit.")
        self.serialized_bundles = len(outputs)
        self.serialized_bytes = sum(map(len, outputs.values()))


def choose_cards(rows, game_region, asset_region):
    """Mirror the GUI's preferred region/common fallback, including all profiles."""
    groups = {}
    for row in rows:
        if (
            row["game_region"] != game_region
            or row["asset_region"] not in {asset_region, "common"}
            or row["card_id"] is None
        ):
            continue
        groups.setdefault(row["card_id"], {}).setdefault(
            row["asset_region"], []
        ).append(row)
    cards = []
    for card, regions in groups.items():
        selected = next(
            (
                regions[region]
                for region in (asset_region, "common")
                if any(r["role"] == "skeleton_json" for r in regions.get(region, []))
            ),
            None,
        )
        if selected:
            cards.append(
                {
                    "card_id": card,
                    "display_name": next(
                        (r["display_name"] for r in selected if r["display_name"]),
                        f"Card {card}",
                    ),
                    "asset_region": selected[0]["asset_region"],
                    "rows": selected,
                }
            )
    return sorted(
        cards, key=lambda card: (card["display_name"].casefold(), card["card_id"])
    )


def synthetic_sources(folder):
    """Two-frame inputs with opaque artwork and transparent padding."""
    folder = Path(folder)
    pngs = folder / "png"
    pngs.mkdir()
    images = []
    for index, color in enumerate(("#f05a70", "#22bb88")):
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((4 + index * 2, 4, 24, 26), fill=color)
        image.save(pngs / f"frame{index + 1}.png")
        images.append(image)
    gif = folder / "animation.gif"
    images[0].save(
        gif,
        save_all=True,
        append_images=images[1:],
        duration=[100, 100],
        disposal=2,
        loop=0,
        transparency=0,
    )
    return {"png": pngs, "gif": gif}


def plan_signature(plan):
    """Deduplicate native serialization only when generated pixels/timing agree."""
    digest = hashlib.sha256()
    for frame in plan["frames"]:
        digest.update(str(frame.size).encode())
        digest.update(frame.tobytes())
    digest.update(
        json.dumps(
            {
                key: plan[key]
                for key in (
                    "indices",
                    "times",
                    "duration",
                    "animation_name",
                    "quality_bindings",
                    "selected_qualities",
                    "lower_quality",
                    "checksums",
                    "rows",
                )
            },
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()


def clean_error(error, installation):
    """Keep private installation directories out of shareable reports."""
    message = str(error)
    for source in ("local", "streaming"):
        try:
            root = str(installation.root(source))
        except ValueError:
            continue
        for spelling in (root, root.replace("\\", "/"), root.replace("/", "\\")):
            message = message.replace(spelling, f"[{source} assets]")
    return message


def audit_card(service, card, sources, options, *, preview_only=False):
    """Probe every available quality with both formats; never write game files."""
    rows = card["rows"]
    result = {key: card[key] for key in ("card_id", "display_name", "asset_region")}
    result["cases"] = []
    missing = set()
    for row in rows:
        try:
            if not service.resolve(row).is_file():
                missing.add(row["source"] + "/" + row["bundle"])
        except FileNotFoundError:
            missing.add(row["source"] + "/" + row["bundle"])
        except (ValueError, OSError) as error:
            result.update(
                status="failed", error=clean_error(error, service.installation)
            )
            return result
    if missing:
        result.update(status="missing_assets", missing_bundles=sorted(missing))
        return result
    qualities = {row["quality"] for row in rows if row["role"] == "skeleton_json"}
    # A graph failure is shared by all formats/qualities; probe it only once.
    from services.summon_animation_service import _Operation
    from unity.summon_flipbook_graph import FlipbookGraph
    import gc

    try:
        operation = _Operation(service)
        FlipbookGraph(service, operation, rows).validate()
    except Exception as error:
        for lower in (False, True):
            if any((quality == "sd") == lower for quality in qualities):
                result["cases"].extend(
                    {
                        "quality": "lower" if lower else "high",
                        "format": source_format,
                        "status": "failed",
                        "stage": "graph",
                        "error_type": type(error).__name__,
                        "error": clean_error(error, service.installation),
                    }
                    for source_format in sources
                )
        result["status"] = "failed"
        return result
    # Keep metadata for every dependency/shared bundle, avoiding repeated
    # full-catalog filesystem walks in affected_components during each probe.
    result["asset_checksums"] = [
        {
            "source": service._location(path)[0],
            "bundle": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for path, (_, payload) in operation.loaded.items()
    ]
    loaded = {(service._location(path)[0], path.name) for path in operation.loaded}
    del operation
    gc.collect()
    original_rows = service.rows
    service.rows = [
        row for row in original_rows if (row["source"], row["bundle"]) in loaded
    ]
    try:
        return _probe_cases(
            service, rows, sources, options, qualities, result, preview_only
        )
    finally:
        service.rows = original_rows


def _probe_cases(service, rows, sources, options, qualities, result, preview_only):
    """Run real previews/serialization against the verified dependency closure."""
    for lower in (False, True):
        if not any((quality == "sd") == lower for quality in qualities):
            continue
        verified = {}
        for source_format, source in sources.items():
            case = {"quality": "lower" if lower else "high", "format": source_format}
            stage = "preview"
            try:
                plan = service.prepare_frame_animation(
                    rows, source, options, lower_quality=lower
                )
                case.update(
                    animation_name=plan["animation_name"],
                    duration=plan["duration"],
                    selected_qualities=plan["selected_qualities"],
                    quality_warning=plan["quality_warning"],
                )
                if not preview_only:
                    stage = "serialization"
                    signature = plan_signature(plan)
                    if signature in verified:
                        case["serialization_reused_from"] = verified[signature]
                    else:
                        service.apply_frame_animation(plan)
                        case["serialized_bundles"] = service.serialized_bundles
                        case["serialized_bytes"] = service.serialized_bytes
                        verified[signature] = source_format
                case.update(status="passed", stage=stage)
            except Exception as error:
                case.update(
                    status="failed",
                    stage=stage,
                    error_type=type(error).__name__,
                    error=clean_error(error, service.installation),
                )
            result["cases"].append(case)
    result["status"] = (
        "failed"
        if any(case["status"] == "failed" for case in result["cases"])
        else "passed"
    )
    return result
