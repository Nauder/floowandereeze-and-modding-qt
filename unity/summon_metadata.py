"""Validated, lossless ETL contract for summon cut-in components."""

import json
import re

COLUMNS = (
    "game_region",
    "source",
    "bundle",
    "asset_path",
    "card_id",
    "display_name",
    "asset_region",
    "quality",
    "scale",
    "role",
    "object_type",
    "path_id",
    "serialized_file",
    "asset_name",
    "width",
    "height",
    "spine_version",
    "animation_names",
    "atlas_pages",
    "external_references",
)
IDENTITY = ("game_region", "source", "bundle", "asset_path")
ROLES = {
    "texture",
    "skeleton_json",
    "atlas",
    "material",
    "prefab",
    "timeline",
    "skeleton_data",
    "atlas_asset",
    "animation",
    "animation_clip",
    "other",
}
ARRAYS = ("animation_names", "atlas_pages", "external_references")


def identity(row):
    """Names and bundle numbers alone are never component identities."""
    return tuple(row[key] for key in IDENTITY)


def validate_row(row):
    """Reject malformed values before starting a database transaction."""
    if set(COLUMNS) - row.keys():
        raise ValueError(
            "Summon metadata schema is incomplete; update the ETL dataset."
        )
    row = {key: row[key] for key in COLUMNS}
    for key in COLUMNS:
        value = row[key]
        if value is not None and key not in ("width", "height"):
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text (IDs must retain all digits).")
    for key, allowed in (
        ("game_region", {"global", "ocg"}),
        ("source", {"local", "streaming"}),
        ("asset_region", {"tcg", "ocg", "common"}),
        ("role", ROLES),
    ):
        if row[key] not in allowed:
            raise ValueError(f"Invalid {key}: {row[key]}")
    if not re.fullmatch(r"[0-9a-fA-F]{8}", row["bundle"] or ""):
        raise ValueError("Invalid bundle filename.")
    if not row["asset_path"] or not row["asset_path"].startswith(
        "assets/resourcesassetbundle/duel/timeline/duel/monstercutin/"
    ):
        raise ValueError("Invalid summon container path.")
    for key, pattern in (
        ("card_id", r"[0-9]+"),
        ("path_id", r"-?[0-9]+"),
        ("scale", r"[0-9]+(?:\.[0-9]+)?"),
    ):
        if row[key] is not None and not re.fullmatch(pattern, row[key]):
            raise ValueError(f"Invalid decimal {key}.")
    for key in ("width", "height"):
        value = row[key]
        if value is not None:
            if isinstance(value, bool) or int(value) != value or value <= 0:
                raise ValueError(f"Invalid {key}.")
            row[key] = int(value)
    for key in ARRAYS:
        if row[key] is not None:
            value = json.loads(row[key])
            if not isinstance(value, list) or any(
                not isinstance(v, str) for v in value
            ):
                raise ValueError(f"{key} must be a JSON array of strings.")
    return row


def component_dict(asset):
    """Detach metadata from ORM objects before sending work to a Qt worker."""
    return {key: getattr(asset, key) for key in COLUMNS}
