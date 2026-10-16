"""Bounded GIF/MP4/PNG decoding and generated Spine attachment timelines."""

from dataclasses import dataclass
from pathlib import Path
import io
import json
import math
import re
from itertools import count

import numpy as np
from PIL import Image, ImageOps

from unity.summon_spine import parse_atlas, validate_spine, validate_regions


@dataclass(frozen=True)
class AtlasSheet:
    """Small frame patches; allocate the full atlas only during texture encoding."""

    size: tuple
    patches: tuple

    def render(self):
        """Create one physical page with transparent background and frame gutters."""
        image = Image.new("RGBA", self.size)
        try:
            for patch, position in self.patches:
                image.paste(patch, position)
        except Exception:
            image.close()
            raise
        return image


@dataclass(frozen=True)
class FrameOptions:
    """Settings independent of the source Spine project."""

    fps: int = 30
    png_fps: int = 30
    edge: int = 256
    framing: str = "fit"
    timing: str = "fit"
    size: int = 100
    x: int = 0
    y: int = 0

    def validate(self):
        """Reject values outside the supported conversion budgets."""
        for name, low, high in (
            ("fps", 1, 60),
            ("png_fps", 1, 60),
            ("edge", 32, 1024),
            ("size", 10, 200),
            ("x", -100, 100),
            ("y", -100, 100),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Invalid {name}: expected {low}–{high}.")
        if self.framing not in {"fit", "crop"} or self.timing not in {"fit", "source"}:
            raise ValueError("Invalid framing or timing mode.")


def natural_key(path):
    """Numbered frames sort 1, 2, 10, with a filename tie-break."""
    name = Path(path).name
    return (
        tuple(
            (1, int(part)) if part.isdigit() else (0, part.casefold())
            for part in re.split(r"(\d+)", name)
        ),
        name,
    )


class ImportMemoryWarning(ValueError):
    """Import needs explicit approval before allocating decoded frame storage."""


def _check_import_memory(source, paths, canvas):
    """Read headers/metadata, without retaining or resizing decoded frames."""
    largest = 0
    frame_count = 0
    unknown = False
    if source.is_file() and source.suffix.lower() == ".mp4":
        try:
            import av
        except ImportError as error:
            raise ValueError(
                "MP4 support requires PyAV. Install the application's requirements."
            ) from error

        try:
            with av.open(str(source)) as container:
                if not container.streams.video:
                    raise ValueError("MP4 contains no video stream.")
                stream = container.streams.video[0]
                largest = stream.codec_context.width * stream.codec_context.height
                frame_count = stream.frames
                if not frame_count and stream.duration and stream.average_rate:
                    frame_count = math.ceil(
                        stream.duration * stream.time_base * stream.average_rate
                    )
                unknown = not frame_count or not largest
        except av.FFmpegError as error:
            raise ValueError(f"Could not decode MP4 video: {error}") from error
    else:
        for path in paths:
            with Image.open(path) as image:
                expected = "PNG" if source.is_dir() else "GIF"
                if image.format != expected:
                    raise ValueError(f"Expected {expected} input: {path.name}.")
                frames = getattr(image, "n_frames", 1)
                if expected == "PNG" and frames != 1:
                    raise ValueError(
                        "Animated PNG is unsupported; use individual PNG files."
                    )
                frame_count += frames
                largest = max(largest, image.width * image.height)
    retained = frame_count * canvas[0] * canvas[1] * 4
    # Resized images plus preparation copies and several full-size decoder buffers.
    estimated = retained * 2 + largest * 16
    if unknown or estimated > 512 * 1024**2 or retained > 128 * 1024**2:
        estimate = (
            "Memory use could not be estimated reliably from this file."
            if unknown
            else f"Estimated working memory: {estimated / 1024**2:,.0f} MiB "
            f"for {frame_count:,} source frames."
        )
        raise ImportMemoryWarning(
            estimate + "\nActual memory use may be higher. This import may take "
            "a long time or exhaust available memory.\n\nContinue importing?"
        )


def decode_frames(source, options, aspect, *, allow_large_import=False):
    """Decode composited GIF frames, MP4 video or naturally ordered PNGs."""
    options.validate()
    source = Path(source)
    paths = sorted(source.glob("*"), key=natural_key) if source.is_dir() else [source]
    paths = [
        p
        for p in paths
        if p.is_file() and (not source.is_dir() or p.suffix.lower() == ".png")
    ]
    if not paths:
        raise ValueError("Choose a GIF, MP4 or a folder containing PNG frames.")
    width = options.edge if aspect >= 1 else max(1, round(options.edge * aspect))
    height = max(1, round(options.edge / aspect)) if aspect >= 1 else options.edge
    canvas = (width, height)
    if not allow_large_import:
        _check_import_memory(source, paths, canvas)
    if source.is_file() and source.suffix.lower() == ".mp4":
        return _decode_video(source, options, canvas)
    images, delays = [], []
    for path in paths:
        with Image.open(path) as image:
            expected = "PNG" if source.is_dir() else "GIF"
            if image.format != expected:
                raise ValueError(f"Expected {expected} input: {path.name}.")
            if expected == "PNG" and getattr(image, "n_frames", 1) != 1:
                raise ValueError(
                    "Animated PNG is unsupported; use individual PNG files."
                )
            for index in (range(1) if expected == "PNG" else count()):
                try:
                    image.seek(index)
                except EOFError:
                    break
                frame = image.convert("RGBA")
                if options.framing == "crop":
                    frame = ImageOps.fit(frame, canvas, method=Image.Resampling.LANCZOS)
                else:
                    resized = ImageOps.contain(
                        frame, canvas, method=Image.Resampling.LANCZOS
                    )
                    frame = Image.new("RGBA", canvas)
                    frame.paste(
                        resized,
                        ((width - resized.width) // 2, (height - resized.height) // 2),
                    )
                images.append(frame)
                delay = (
                    max(10, image.info.get("duration", 100) or 100) / 1000
                    if expected == "GIF"
                    else 1 / options.png_fps
                )
                delays.append(delay)
    return images, delays


def _decode_video(source, options, canvas):
    """Decode only the first video stream, retaining presentation-time intervals."""
    try:
        import av
    except ImportError as error:
        raise ValueError(
            "MP4 support requires PyAV. Install the application's requirements."
        ) from error

    images, delays, timestamps = [], [], []
    try:
        with av.open(str(source)) as container:
            if not container.streams.video:
                raise ValueError("MP4 contains no video stream.")
            stream = container.streams.video[0]
            rate = float(stream.average_rate or 0)
            fallback = 1 / rate if math.isfinite(rate) and rate > 0 else None
            for frame in container.decode(stream):
                timestamp = frame.time
                delay = (
                    float(frame.duration * frame.time_base)
                    if frame.duration and frame.time_base
                    else fallback
                )
                if delay is None or not math.isfinite(delay) or delay <= 0:
                    raise ValueError("MP4 has no valid frame timing.")
                if timestamp is None or not math.isfinite(timestamp):
                    raise ValueError("MP4 has no valid frame timestamps.")
                if timestamps:
                    interval = timestamp - timestamps[-1]
                    if interval <= 0:
                        raise ValueError("MP4 frame timestamps must increase.")
                    delays[-1] = interval
                timestamps.append(timestamp)
                delays.append(delay)
                with frame.to_image() as image:
                    with image.convert("RGBA") as rgba:
                        if options.framing == "crop":
                            fitted = ImageOps.fit(
                                rgba, canvas, method=Image.Resampling.LANCZOS
                            )
                        else:
                            fitted = Image.new("RGBA", canvas)
                            with ImageOps.contain(
                                rgba, canvas, method=Image.Resampling.LANCZOS
                            ) as resized:
                                fitted.paste(
                                    resized,
                                    (
                                        (canvas[0] - resized.width) // 2,
                                        (canvas[1] - resized.height) // 2,
                                    ),
                                )
                        images.append(fitted)
            if not images:
                raise ValueError("MP4 contains no decodable video frames.")
        return images, delays
    except Exception as error:
        for image in images:
            image.close()
        if isinstance(error, ValueError) and not isinstance(error, av.FFmpegError):
            raise
        raise ValueError(f"Could not decode MP4 video: {error}") from error


def sample_frames(images, delays, duration, options):
    """Resample delays; source mode trims long input and holds short input."""
    if not math.isfinite(duration) or not 0 < duration <= 10:
        raise ValueError("Only finite summon clips up to ten seconds are supported.")
    count = math.ceil(duration * options.fps)
    ends, total = [], 0
    for delay in delays:
        total += delay
        ends.append(total)
    indices, times = [], []
    cursor = 0
    for index in range(count):
        time = duration * index / count
        source_time = time * total / duration if options.timing == "fit" else time
        while cursor < len(ends) - 1 and (
            source_time >= ends[cursor]
            or math.isclose(source_time, ends[cursor], rel_tol=0, abs_tol=1e-9)
        ):
            cursor += 1
        indices.append(cursor)
        times.append(time)
    selected = list(dict.fromkeys(indices))
    return (
        [images[index] for index in selected],
        [selected.index(index) for index in indices],
        times,
    )


def generate_project(
    original,
    pages,
    frames,
    indices,
    times,
    duration,
    options,
    animation_name=None,
    region_prefix="floo_frame",
    reserve_blank=False,
    lazy=False,
):
    """Keep existing pages/material pointers while generating a new simple rig."""
    width, height = frames[0].size
    pitch_x, pitch_y = width + 4, height + 4
    capacity = sum(
        (p["size"][0] // pitch_x) * (p["size"][1] // pitch_y)
        - (1 if reserve_blank and _blank_cell(p, pitch_x, pitch_y) else 0)
        for p in pages
    )
    if len(frames) > capacity:
        raise ValueError(
            f"{len(frames)} distinct frames need more than {capacity} atlas cells. Lower frame resolution or FPS."
        )
    page_bytes = [p["size"][0] * p["size"][1] * 4 for p in pages]
    if any(size > 256 * 1024**2 for size in page_bytes):
        raise ValueError("An atlas page exceeds the 256 MiB conversion limit.")
    if not lazy and sum(page_bytes) > 256 * 1024**2:
        raise ValueError("Atlas memory exceeds the 256 MiB conversion limit.")
    sheets, texts, names = [], [], []
    frame_index = 0
    for page in pages:
        patches = []
        lines = [
            page["name"],
            f"size: {page['size'][0]},{page['size'][1]}",
            "filter: Linear,Linear",
            f"pma: {'true' if page['pma'] else 'false'}",
        ]
        columns, rows = page["size"][0] // pitch_x, page["size"][1] // pitch_y
        cells = columns * rows - (
            1 if reserve_blank and _blank_cell(page, pitch_x, pitch_y) else 0
        )
        for cell in range(max(0, cells)):
            if frame_index == len(frames):
                break
            name = f"{region_prefix}_{frame_index:04d}"
            names.append(name)
            x, y = (cell % columns) * pitch_x + 2, (cell // columns) * pitch_y + 2
            image = frames[frame_index]
            if page["pma"]:
                pixels = np.array(image, dtype=np.uint16)
                pixels[:, :, :3] = (pixels[:, :, :3] * pixels[:, :, 3:4] + 127) // 255
                image = Image.fromarray(pixels.astype(np.uint8), "RGBA")
            padded = Image.fromarray(
                np.pad(np.array(image), ((2, 2), (2, 2), (0, 0)), mode="edge")
            )
            patches.append((padded, (x - 2, y - 2)))
            lines.extend(
                [
                    name,
                    f"bounds: {x},{y},{width},{height}",
                    f"offsets: 0,0,{width},{height}",
                    "rotate: false",
                ]
            )
            frame_index += 1
        if len(lines) == 4:
            lines.extend(
                [
                    f"floo_unused_{len(sheets)}",
                    "bounds: 2,2,1,1",
                    "offsets: 0,0,1,1",
                    "rotate: false",
                ]
            )
        sheet = AtlasSheet(page["size"], tuple(patches))
        sheets.append(sheet if lazy else sheet.render())
        texts.append("\n".join(lines))
    bounds = original["skeleton"]
    logical_width, logical_height = float(bounds["width"]), float(bounds["height"])
    attachments = {
        name: {
            "type": "region",
            "path": name,
            "x": float(bounds.get("x", 0))
            + logical_width / 2
            + logical_width * options.x / 100,
            "y": float(bounds.get("y", 0))
            + logical_height / 2
            + logical_height * options.y / 100,
            "width": logical_width * options.size / 100,
            "height": logical_height * options.size / 100,
        }
        for name in names
    }
    if animation_name is None:
        if len(original["animations"]) != 1:
            raise ValueError(
                "Select the timeline animation for a multi-animation skeleton."
            )
        animation_name = next(iter(original["animations"]))
    if animation_name not in original["animations"]:
        raise ValueError("Timeline animation is missing from the skeleton.")

    def key_times(value):
        if isinstance(value, dict):
            if "time" in value:
                time = value["time"]
                if (
                    not isinstance(time, (int, float))
                    or not math.isfinite(time)
                    or time < 0
                ):
                    raise ValueError("Invalid original animation keyframe time.")
                yield time
            for child in value.values():
                yield from key_times(child)
        elif isinstance(value, list):
            for child in value:
                yield from key_times(child)

    animations = {}
    for name, source_animation in original["animations"].items():
        span = (
            duration
            if name == animation_name
            else max(key_times(source_animation), default=0)
        )
        if span:
            keys = [
                {"time": time * span / duration, "name": names[index]}
                for time, index in zip(times, indices)
            ]
            keys.append({"time": span, "name": keys[-1]["name"]})
        else:
            keys = [{"time": 0, "name": names[indices[0]]}]
        animation = {"slots": {"frames": {"attachment": keys}}}
        if "events" in source_animation:
            animation["events"] = source_animation["events"]
        animations[name] = animation
    project = {
        "skeleton": dict(bounds, hash="floo-generated-flipbook"),
        "bones": [{"name": "root"}],
        "slots": [{"name": "frames", "bone": "root", "attachment": names[indices[0]]}],
        "skins": [{"name": "default", "attachments": {"frames": attachments}}],
        "animations": animations,
    }
    if "events" in original:
        project["events"] = original["events"]
    payload = json.dumps(project, allow_nan=False).encode()
    atlas = ("\n\n".join(texts) + "\n").encode()
    validate_spine(payload, bounds["spine"])
    validate_regions(project, parse_atlas(atlas))
    return payload, atlas, sheets


def preview_pngs(frames):
    """Small straight-alpha previews can transfer to the GUI thread."""
    result = []
    for frame in frames:
        image = frame.copy()
        image.thumbnail((512, 512))
        output = io.BytesIO()
        image.save(output, format="PNG")
        result.append(output.getvalue())
    return result


def _blank_cell(page, pitch_x, pitch_y):
    """Reserve a transparent gutter for legacy regions without stealing spare space."""
    width, height = page["size"]
    return width % pitch_x < 8 and height % pitch_y < 8


def generate_quality_projects(
    profiles,
    frames,
    indices,
    times,
    duration,
    options,
    animation_name,
    lower_quality=False,
    selected_qualities=None,
):
    """Preserve shared rig indices and render new frames only in the selected quality."""
    from copy import deepcopy

    selected = (
        [p for p in profiles if p[1]["quality"] in selected_qualities]
        if selected_qualities is not None
        else [p for p in profiles if (p[1]["quality"] == "sd") == lower_quality]
    )
    if not selected:
        label = "lower" if lower_quality else "high"
        raise ValueError(f"No {label}-quality animation is available for this card.")

    # AnimationReferenceAsset can supply animations from a different profile.
    # Retain the original rig and append identical independent frame slots everywhere.
    def topology(project):
        return (
            [(b["name"], b.get("parent")) for b in project["bones"]],
            [(s["name"], s["bone"]) for s in project.get("slots", [])],
            [
                [c["name"] for c in project.get(kind, [])]
                for kind in ("ik", "transform", "path", "physics")
            ],
        )

    if any(topology(p[4]) != topology(profiles[0][4]) for p in profiles):
        raise ValueError("Quality profiles have incompatible playback structures.")
    projects = [deepcopy(p[4]) for p in profiles]
    outputs = {}
    for target in selected:
        quality = target[1]["quality"]
        if not quality or not re.fullmatch(r"[a-zA-Z0-9_]+", quality):
            raise ValueError("Unsupported quality identifier.")
        slot_name, bone_name = "floo_frames_" + quality, "floo_root_" + quality
        original = target[4]
        for skin in original.get("skins", []):
            for entries in skin.get("attachments", {}).values():
                for attachment in entries.values():
                    if attachment.get("sequence"):
                        raise ValueError("Sequence attachments are unsupported.")
                    if any(
                        not math.isfinite(uv) or not 0 <= uv <= 1
                        for uv in attachment.get("uvs", [])
                    ):
                        raise ValueError(
                            "Mesh UVs outside their atlas region are unsupported."
                        )
        # Rebuild selected pages at their actual Unity texture dimensions.
        # Original atlas coordinates remain valid for the untouched profiles.
        target_pages = deepcopy(target[5])
        for page in target_pages:
            page["size"] = page.get("texture_size", page["size"])
        payload, atlas, sheets = generate_project(
            original,
            target_pages,
            frames,
            indices,
            times,
            duration,
            options,
            animation_name=animation_name,
            region_prefix=slot_name,
            reserve_blank=True,
            lazy=True,
        )
        generated = json.loads(payload)
        attachments = generated["skins"][0]["attachments"]["frames"]
        # Original attachments remain parseable but sample a guaranteed transparent
        # cell in this profile. Its old animation/deform data stays valid.
        generated_regions = {
            r["name"] for p in parse_atlas(atlas) for r in p["regions"]
        }
        chunks = atlas.decode().strip().split("\n\n")
        for chunk_index, page in enumerate(target_pages):
            x, y = (
                (page["size"][0] - 4) // 4 * 4 + 1,
                (page["size"][1] - 4) // 4 * 4 + 1,
            )
            aliases = [
                f"{region['name']}\nbounds: {x},{y},1,1\noffsets: 0,0,1,1\nrotate: false"
                for region in page["regions"]
                if region["name"] not in generated_regions
            ]
            chunks[chunk_index] += "\n" + "\n".join(aliases)
        atlas = ("\n\n".join(chunks) + "\n").encode()
        outputs[id(target)] = (atlas, sheets)
        for profile, project in zip(profiles, projects):
            markers = project.setdefault("flooQualityFrames", {})
            if slot_name not in markers:
                if any(b["name"] == bone_name for b in project["bones"]) or any(
                    s["name"] == slot_name for s in project["slots"]
                ):
                    raise ValueError(
                        "Reserved frame names conflict with this skeleton."
                    )
                project["bones"].append({"name": bone_name})
                project["slots"].append({"name": slot_name, "bone": bone_name})
                markers[slot_name] = {"quality": quality}
            if profile is target:
                legacy_slots = [
                    s["name"]
                    for s in project["slots"]
                    if not s["name"].startswith("floo_frames_")
                ]
                for skin in project.get("skins", []):
                    for entries in skin.get("attachments", {}).values():
                        for attachment in entries.values():
                            if attachment.get(
                                "type"
                            ) == "clipping" and not attachment.get("end"):
                                attachment["end"] = legacy_slots[-1]
            slot = next(s for s in project["slots"] if s["name"] == slot_name)
            slot["attachment"] = next(iter(attachments))
            skins = project.setdefault("skins", [])
            if not any(s["name"] == "default" for s in skins):
                skins.insert(0, {"name": "default", "attachments": {}})
            for skin in skins:
                skin.setdefault("attachments", {})[slot_name] = (
                    deepcopy(attachments)
                    if profile is target
                    else {name: {"type": "point"} for name in attachments}
                )
            for name, animation in project["animations"].items():
                animation.setdefault("slots", {})[slot_name] = deepcopy(
                    generated["animations"][name]["slots"]["frames"]
                )
            project["skeleton"]["hash"] = "floo-quality-flipbook"
    changes = []
    for profile, project in zip(profiles, projects):
        payload = json.dumps(project, allow_nan=False).encode()
        validate_spine(payload, profile[4]["skeleton"]["spine"])
        if id(profile) in outputs:
            atlas, sheets = outputs[id(profile)]
            validate_regions(project, parse_atlas(atlas))
            changes.extend([(profile[1], payload), (profile[2], atlas)])
            changes.extend(zip(profile[3], sheets))
        else:
            validate_regions(project, profile[5])
            changes.append((profile[1], payload))
    return changes
