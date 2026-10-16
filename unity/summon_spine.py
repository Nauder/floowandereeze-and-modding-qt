"""Conservative Spine 4 atlas/project validation, without runtime conversion."""

import json
from pathlib import PurePosixPath


def text_bytes(data):
    """UnityPy TextAssets use surrogateescape for arbitrary binary payloads."""
    value = data.m_Script
    return (
        value if isinstance(value, bytes) else value.encode("utf-8", "surrogateescape")
    )


def parse_atlas(payload):
    """Parse page headers and packed regions, retaining rotation and PMA."""
    text = payload.decode("utf-8", "strict") if isinstance(payload, bytes) else payload
    pages, page, region, blank = [], None, None, True
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            blank = True
            region = None
            continue
        if ":" not in line:
            if blank or page is None:
                if (
                    PurePosixPath(line).name != line
                    or "\\" in line
                    or line in (".", "..")
                ):
                    raise ValueError("Atlas page names must be simple filenames.")
                page = {"name": line, "pma": False, "regions": []}
                pages.append(page)
                region = None
            else:
                if page is None:
                    raise ValueError("Atlas region has no page.")
                region = {"name": line, "rotate": False}
                # The guard above validates page; Pylint loses this loop state.
                # pylint: disable-next=unsubscriptable-object
                page["regions"].append(region)
            blank = False
            continue
        if page is None:
            raise ValueError("Atlas has properties before its first page.")
        key, value = [part.strip() for part in line.split(":", 1)]
        target = region if region is not None else page
        if key in ("size", "xy", "bounds"):
            try:
                target[key] = tuple(int(v.strip()) for v in value.split(","))
            except ValueError as error:
                raise ValueError("Invalid atlas coordinates.") from error
        elif key == "pma":
            if region is not None or value not in ("true", "false"):
                raise ValueError("Invalid atlas PMA declaration.")
            page["pma"] = value == "true"
        elif key == "rotate":
            if value not in ("true", "false", "0", "90", "180", "270"):
                raise ValueError("Unsupported atlas rotation.")
            target[key] = value in ("true", "90", "270")
    if not pages or len({p["name"].casefold() for p in pages}) != len(pages):
        raise ValueError("Atlas page names are empty or ambiguous.")
    names = []
    for page in pages:
        if len(page.get("size", ())) != 2 or min(page["size"]) <= 0:
            raise ValueError("Atlas page dimensions are required.")
        for region in page["regions"]:
            names.append(region["name"])
            if "bounds" in region:
                if len(region["bounds"]) != 4:
                    raise ValueError("Invalid atlas bounds.")
                x, y, w, h = region["bounds"]
            else:
                if len(region.get("xy", ())) != 2 or len(region.get("size", ())) != 2:
                    raise ValueError("Atlas region has no packed bounds.")
                x, y = region["xy"]
                w, h = region["size"]
            if region["rotate"]:
                w, h = h, w
            if (
                min(x, y) < 0
                or min(w, h) <= 0
                or x + w > page["size"][0]
                or y + h > page["size"][1]
            ):
                raise ValueError(f"Atlas region {region['name']} is outside its page.")
            region["rectangle"] = (x, y, x + w, y + h)
    if len(set(names)) != len(names):
        raise ValueError("Duplicate atlas regions are unsupported.")
    return pages


def validate_spine(payload, version=None):
    """Validate references before a compatible project can be imported."""

    def invalid_constant(value):
        raise ValueError(f"Invalid non-finite JSON number: {value}")

    project = json.loads(payload, parse_constant=invalid_constant)
    if not isinstance(project, dict) or not isinstance(project.get("skeleton"), dict):
        raise ValueError("Invalid Spine skeleton JSON.")
    actual = project["skeleton"].get("spine")
    if not actual or (version is not None and actual != version):
        raise ValueError(
            f"Spine version must match exactly: expected {version}, got {actual}."
        )
    bones, slots = project.get("bones"), project.get("slots", [])
    if not isinstance(bones, list) or not bones or not isinstance(slots, list):
        raise ValueError("Spine bones/slots must be arrays.")
    bone_names, slot_names = set(), set()
    for bone in bones:
        name = bone.get("name")
        if (
            not name
            or name in bone_names
            or (bone.get("parent") and bone["parent"] not in bone_names)
        ):
            raise ValueError("Invalid or duplicate bone reference.")
        bone_names.add(name)
    for slot in slots:
        if (
            not slot.get("name")
            or slot["name"] in slot_names
            or slot.get("bone") not in bone_names
        ):
            raise ValueError("Invalid or duplicate slot reference.")
        slot_names.add(slot["name"])
    animations = project.get("animations", {})
    if not isinstance(animations, dict):
        raise ValueError("Spine animations must be an object.")
    for animation in animations.values():
        if not isinstance(animation, dict):
            raise ValueError("Invalid animation definition.")
        if (
            set(animation.get("bones", {})) - bone_names
            or set(animation.get("slots", {})) - slot_names
        ):
            raise ValueError("Animation references an unknown bone or slot.")
    skins = project.get("skins", [])
    if not isinstance(skins, list):
        raise ValueError("Only Spine 4 skin arrays are supported.")
    for skin in skins:
        if set(skin.get("attachments", {})) - slot_names:
            raise ValueError("Skin references an unknown slot.")
        if set(skin.get("bones", [])) - bone_names:
            raise ValueError("Skin references an unknown bone.")
    for kind in ("ik", "transform", "path"):
        constraints = project.get(kind, [])
        if not isinstance(constraints, list):
            raise ValueError("Constraint definitions must be arrays.")
        for constraint in constraints:
            if set(constraint.get("bones", [])) - bone_names:
                raise ValueError("Constraint references an unknown bone.")
            targets = slot_names if kind == "path" else bone_names
            if constraint.get("target") not in targets:
                raise ValueError("Constraint references an unknown target.")
    return project


def validate_regions(project, pages):
    """Every textured skin attachment must have a packed atlas region."""
    regions = {region["name"] for page in pages for region in page["regions"]}
    attachments = {}
    for skin in project.get("skins", []):
        for slot, entries in skin.get("attachments", {}).items():
            attachments.setdefault(slot, set()).update(entries)
            for name, attachment in entries.items():
                kind = attachment.get("type", "region")
                if kind in {"region", "mesh", "linkedmesh"}:
                    if attachment.get("sequence"):
                        raise ValueError(
                            "Sequence attachments require a future format adapter."
                        )
                    if attachment.get("path", name) not in regions:
                        raise ValueError(f"Attachment {name} has no atlas region.")
    for slot in project.get("slots", []):
        if slot.get("attachment") and slot["attachment"] not in attachments.get(
            slot["name"], set()
        ):
            raise ValueError("Slot references an unknown attachment.")
    for animation in project.get("animations", {}).values():
        for slot, timelines in animation.get("slots", {}).items():
            for frame in timelines.get("attachment", []):
                if frame.get("name") is not None and frame[
                    "name"
                ] not in attachments.get(slot, set()):
                    raise ValueError("Animation references an unknown attachment.")


def graph_signature(value, key=""):
    """Keep names, topology, frame counts and times stable for Unity wrappers.

    Numeric pose/curve values may change. New attachment layouts, animations,
    events, timelines or cached durations require a future wrapper adapter.
    """
    if isinstance(value, dict):
        return {k: graph_signature(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [graph_signature(v, key) for v in value]
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and key != "time"
    ):
        return "<number>"
    return value


def validate_compatible(original, imported, atlas, imported_atlas):
    """Accept only same-runtime projects with unchanged wrapper/atlas structure."""
    target = validate_spine(original)
    incoming = validate_spine(imported, target["skeleton"]["spine"])
    if graph_signature(target) != graph_signature(incoming):
        raise ValueError(
            "Import changes graph/names/timing; a Unity wrapper adapter is required."
        )
    before, after = parse_atlas(atlas), parse_atlas(imported_atlas)
    if before != after:
        raise ValueError(
            "Atlas layout, page names, dimensions and PMA must remain unchanged."
        )
    validate_regions(incoming, after)
    return incoming, after


def validate_image(image, page, alpha_mode):
    """PMA is declared by the user and checked for impossible channel values."""
    if image.mode != "RGBA" or image.size != tuple(page["size"]):
        raise ValueError(
            "Page replacement must be an RGBA image with identical dimensions."
        )
    expected = "premultiplied" if page["pma"] else "straight"
    if alpha_mode != expected:
        raise ValueError(f"This atlas requires {expected} alpha input.")
    if page["pma"]:
        import numpy as np

        pixels = np.asarray(image)
        if (pixels[:, :, :3] > pixels[:, :, 3:4]).any():
            raise ValueError("Image channels exceed alpha; input is not premultiplied.")
