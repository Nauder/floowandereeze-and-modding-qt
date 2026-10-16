"""Explicit-installation, multi-component summon editing with whole-bundle restore."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from threading import RLock
from dataclasses import dataclass

from PIL import Image, ImageDraw
from UnityPy import load as unity_load

from services.backup_service import BackupService
from unity.summon_metadata import identity, validate_row
from unity.summon_spine import (
    text_bytes,
    parse_atlas,
    validate_spine,
    validate_regions,
    validate_compatible,
    validate_image,
)

_WRITE_LOCK = RLock()


def checksum(payload):
    """Portable SHA-256 for original bundles and staged output."""
    return hashlib.sha256(payload).hexdigest()


def game_running():
    """Fail closed when Windows process inspection is unavailable."""
    if os.name != "nt":
        raise RuntimeError("Game process detection is supported on Windows only.")
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=True,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=10,
    )
    rows = list(csv.reader(io.StringIO(result.stdout)))
    if not rows or any(len(row) < 5 for row in rows):
        raise RuntimeError("Could not inspect Windows process list; editing refused.")
    return any(
        row and row[0].casefold() in {"masterduel.exe", "masterduel"} for row in rows
    )


@dataclass(frozen=True)
class Installation:
    """Roots belong to one explicitly selected global or OCG installation."""

    game_region: str
    local_root: Path
    streaming_root: Path = None

    def __post_init__(self):
        if self.game_region not in {"global", "ocg"}:
            raise ValueError("Select the global or OCG installation explicitly.")
        object.__setattr__(self, "local_root", Path(self.local_root).resolve())
        if self.streaming_root is not None:
            object.__setattr__(
                self, "streaming_root", Path(self.streaming_root).resolve()
            )
            if (
                self.local_root == self.streaming_root
                or self.local_root in self.streaming_root.parents
                or self.streaming_root in self.local_root.parents
            ):
                raise ValueError(
                    "Local and streaming bundle roots must be distinct and non-overlapping."
                )

    @property
    def key(self):
        return checksum(
            json.dumps(
                [self.game_region, str(self.local_root), str(self.streaming_root)]
            ).encode()
        )

    def root(self, source):
        root = {"local": self.local_root, "streaming": self.streaming_root}.get(source)
        if root is None:
            raise ValueError(f"Select the {source} root for this installation.")
        return root

    def path(self, source, relative):
        BackupService._validate_name(relative)
        root = self.root(source)
        path = root.joinpath(*relative.split("/"))
        if root not in path.resolve().parents:
            raise ValueError("Bundle path leaves the selected installation root.")
        return path


def cab_name(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1].casefold()


class _Operation:
    """Load physical bundles once, with validated container/object identities."""

    def __init__(self, service):
        self.service = service
        self.loaded = {}
        self.cabs = {}
        self.discovered = {}

    def load_path(self, path):
        path = path.resolve()
        if path not in self.loaded:
            total = sum(len(payload) for _, payload in self.loaded.values())
            if total + path.stat().st_size > self.service.MAX_LOADED_BYTES:
                raise ValueError(
                    "Bundle/dependency byte limit reached; refresh metadata to avoid broad discovery."
                )
            payload = path.read_bytes()
            env = self.service.loader(payload)
            self.loaded[path] = (env, payload)
            for obj in env.objects:
                name = cab_name(obj.assets_file.name)
                paths = self.cabs.setdefault(name, set())
                paths.add(path)
        return self.loaded[path][0]

    @staticmethod
    def discovery_key(row):
        return (
            *identity(row),
            row["serialized_file"],
            row["path_id"],
            row["object_type"],
        )

    def target(self, row, env=None):
        validate_row(row)
        if row["game_region"] != self.service.installation.game_region:
            raise ValueError(
                "Metadata region does not match the selected installation."
            )
        if any(
            row[k] is None
            for k in ("path_id", "serialized_file", "object_type", "asset_name")
        ):
            raise ValueError(
                "Incomplete object metadata. Refresh metadata before editing."
            )
        path = self.service.resolve(row)
        env = env if env is not None else self.load_path(path)
        discovered = self.discovered.get(self.discovery_key(row))
        if discovered is not None:
            if validate_row(row) != discovered:
                raise ValueError("Discovered playback object identity changed.")
            candidates = [
                obj
                for obj in env.objects
                if str(obj.path_id) == row["path_id"]
                and cab_name(obj.assets_file.name) == cab_name(row["serialized_file"])
            ]
            if len(candidates) != 1:
                raise ValueError("Discovered playback object is missing or ambiguous.")
            obj = candidates[0]
            if obj.type.name != row["object_type"]:
                raise ValueError("Discovered playback object type changed.")
            return path, obj, obj.read()
        candidates = [
            pointer
            for name, pointer in env.container.items()
            if name == row["asset_path"]
        ]
        if len(candidates) > 1:
            # Unity containers can expose sub-assets under one path (prefab
            # meshes, timeline curves). Resolve the exact recorded object.
            candidates = [
                p
                for p in candidates
                if str(p.deref().path_id) == row["path_id"]
                and p.deref().type.name == row["object_type"]
                and cab_name(p.deref().assets_file.name)
                == cab_name(row["serialized_file"])
            ]
        if len(candidates) != 1:
            raise ValueError(
                "Container path is missing or ambiguous; refresh metadata."
            )
        obj = candidates[0].deref()
        if (
            str(obj.path_id) != row["path_id"]
            or obj.type.name != row["object_type"]
            or cab_name(obj.assets_file.name) != cab_name(row["serialized_file"])
        ):
            raise ValueError("Object identifier/type/CAB changed; refresh metadata.")
        data = obj.read()
        if getattr(data, "m_Name", None) != row["asset_name"]:
            raise ValueError("Asset name changed; refresh metadata.")
        if row["role"] == "skeleton_json":
            project = validate_spine(text_bytes(data), row["spine_version"])
            if row["animation_names"] is not None and sorted(
                project.get("animations", {})
            ) != sorted(json.loads(row["animation_names"])):
                raise ValueError("Animation names changed; refresh metadata.")
        actual = [external.path for external in obj.assets_file.externals]
        if row["external_references"] is not None and actual != json.loads(
            row["external_references"]
        ):
            raise ValueError("Serialized dependencies changed; refresh metadata.")
        if obj.type.name == "Texture2D" and (
            (row["width"] is not None and data.m_Width != row["width"])
            or (row["height"] is not None and data.m_Height != row["height"])
        ):
            raise ValueError("Texture dimensions changed; refresh metadata.")
        return path, obj, data

    def dependencies(self, rows):
        """Resolve actual CAB references transitively; unknown local CABs are bounded."""
        todo = []
        for row in rows:
            path, _, _ = self.target(row)
            todo.append(path)
        seen, scanned = set(), False
        while todo:
            path = todo.pop()
            if path in seen:
                continue
            seen.add(path)
            env = self.load_path(path)
            files = {
                id(obj.assets_file): obj.assets_file for obj in env.objects
            }.values()
            for file in files:
                for external in file.externals:
                    name = cab_name(external.path)
                    candidates = [
                        r
                        for r in self.service.rows
                        if r["game_region"] == self.service.installation.game_region
                        and r["serialized_file"]
                        and cab_name(r["serialized_file"]) == name
                    ]
                    for row in candidates:
                        self.load_path(self.service.resolve(row))
                    if name not in self.cabs and not scanned:
                        self._scan_local_cabs()
                        scanned = True
                    matches = self.cabs.get(name, set())
                    if len(matches) != 1:
                        raise ValueError(
                            f"Missing or ambiguous dependency {name}. Download assets/refresh metadata."
                        )
                    todo.extend(matches - seen)
        return sorted(seen)

    def _scan_local_cabs(self):
        count = 0
        for source in ("local", "streaming"):
            try:
                root = self.service.installation.root(source)
            except ValueError:
                continue
            # Only known two-character bucket layout; never recursive extraction.
            for path in root.glob("??/????????"):
                count += 1
                if count > self.service.MAX_DEPENDENCY_BUNDLES:
                    raise ValueError("Dependency scan limit reached; refresh metadata.")
                if path.is_file():
                    relative = path.relative_to(root).as_posix()
                    safe = self.service.installation.path(source, relative)
                    try:
                        self.load_path(safe)
                    except (ValueError, EOFError):
                        continue


class SummonAnimationService:
    """Browse without writes; stage, reload and rollback every editing operation."""

    MAX_DEPENDENCY_BUNDLES = 20000
    MAX_LOADED_BYTES = 512 * 1024**2

    def __init__(
        self,
        installation,
        rows,
        packer="LZ4",
        backup_root="backups",
        loader=None,
        running=None,
    ):
        self.installation = installation
        self.rows = [validate_row(dict(row)) for row in rows]
        self.packer = packer
        self.backups = BackupService(backup_root)
        self.loader = loader or unity_load
        self.running = running or game_running

    def resolve(self, row):
        """Use ETL source within the selected installation; no cross-region fallback."""
        if row["game_region"] != self.installation.game_region:
            raise ValueError("Select a matching installation for this metadata.")
        bundle = row["bundle"]
        path = self.installation.path(row["source"], f"{bundle[:2]}/{bundle}")
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing {row['source']} bundle {bundle}; download it in this installation."
            )
        return path

    def components(self, card_id, asset_region, quality, scale):
        """Include shared card rows, retaining independent page/scale candidates."""
        return [
            r
            for r in self.rows
            if r["game_region"] == self.installation.game_region
            and r["card_id"] == card_id
            and r["asset_region"] == asset_region
            and r["quality"] in (None, quality)
            and r["scale"] in (None, scale)
        ]

    def affected_components(self, rows):
        paths = {self.resolve(row) for row in rows}
        return [
            row
            for row in self.rows
            if row["game_region"] == self.installation.game_region
            and self.installation.path(
                row["source"], f"{row['bundle'][:2]}/{row['bundle']}"
            )
            in paths
        ]

    def _atlas(self, rows, operation, *, allow_resized=False):
        atlases = [r for r in rows if r["role"] == "atlas"]
        if len(atlases) != 1:
            raise ValueError(
                "Select a profile/scale with exactly one atlas; ambiguous graphs are unsupported."
            )
        atlas = atlases[0]
        _, _, data = operation.target(atlas)
        payload = text_bytes(data)
        pages = parse_atlas(payload)
        if atlas["atlas_pages"] is not None and [
            p["name"] for p in pages
        ] != json.loads(atlas["atlas_pages"]):
            raise ValueError("Atlas pages changed; refresh metadata.")
        textures = []
        for page in pages:
            candidates = [
                r
                for r in rows
                if r["role"] == "texture"
                and Path(r["asset_path"]).name.casefold() == page["name"].casefold()
                and r["asset_region"] == atlas["asset_region"]
                and r["quality"] == atlas["quality"]
                and r["scale"] == atlas["scale"]
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"Missing or ambiguous atlas page {page['name']}; select the exact profile/scale."
                )
            texture = candidates[0]
            _, _, data = operation.target(texture)
            if (data.m_Width, data.m_Height) != page["size"] and not allow_resized:
                raise ValueError("Atlas and texture dimensions disagree.")
            # Unity may resize atlas textures during import. Keep original regions
            # for untouched profiles; generated flipbooks use physical dimensions.
            page["texture_size"] = (data.m_Width, data.m_Height)
            textures.append(texture)
        return atlas, payload, pages, textures

    def preview_component(self, row, rows, replacement=None, alpha_mode=None):
        """Return PNG bytes with packed-region overlays; no playback or disk cache."""
        operation = _Operation(self)
        _, _, data = operation.target(row)
        if row["object_type"] != "Texture2D":
            if row["object_type"] == "TextAsset":
                return {"text": text_bytes(data).decode("utf-8", "replace")}
            return {
                "text": "Unity wrapper/timeline component. Export for external inspection."
            }
        _, _, pages, textures = self._atlas(rows, operation)
        page = pages[textures.index(row)]
        image = data.image.copy().convert("RGBA")

        def png(image):
            draw = ImageDraw.Draw(image)
            for region in page["regions"]:
                draw.rectangle(region["rectangle"], outline="#ff00ff", width=2)
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()

        result = {"before": png(image), "pma": page["pma"]}
        if replacement:
            with Image.open(replacement) as incoming:
                validate_image(incoming, page, alpha_mode)
                result["after"] = png(incoming.copy())
        return result

    def export_component(self, row, destination):
        operation = _Operation(self)
        _, obj, data = operation.target(row)
        destination = Path(destination)
        self._export_target(destination)
        if obj.type.name == "Texture2D":
            data.image.save(destination, format="PNG")
        elif obj.type.name == "TextAsset":
            destination.write_bytes(text_bytes(data))
        else:
            destination.write_bytes(obj.get_raw_data())
        return str(destination)

    def _export_target(self, path):
        resolved = Path(path).resolve()
        for root in (
            self.installation.local_root,
            self.installation.streaming_root,
            self.backups.root,
        ):
            if root and (root == resolved or root in resolved.parents):
                raise ValueError(
                    "Choose an export destination outside game and backup roots."
                )

    def export_spine_project(self, rows, destination):
        operation = _Operation(self)
        atlas, atlas_bytes, pages, textures = self._atlas(rows, operation)
        skeletons = [r for r in rows if r["role"] == "skeleton_json"]
        if len(skeletons) != 1:
            raise ValueError("Select exactly one skeleton JSON for project export.")
        skeleton = skeletons[0]
        _, _, data = operation.target(skeleton)
        payload = text_bytes(data)
        project = validate_spine(payload, skeleton["spine_version"])
        validate_regions(project, pages)
        operation.dependencies(rows)
        folder = Path(destination)
        self._export_target(folder)
        files = {"skeleton.json": payload, "skeleton.atlas": atlas_bytes}
        if any(
            p["name"].casefold()
            in {"skeleton.json", "skeleton.atlas", "floo-project.json"}
            for p in pages
        ):
            raise ValueError("Atlas page name conflicts with project metadata.")
        for page, texture in zip(pages, textures):
            _, _, data = operation.target(texture)
            output = io.BytesIO()
            data.image.save(output, format="PNG")
            files[page["name"]] = output.getvalue()
        manifest = {
            "schema": 1,
            "components": [identity(r) for r in rows],
            "spine_version": project["skeleton"]["spine"],
            "animations": list(project.get("animations", {})),
            "pages": [{"name": p["name"], "pma": p["pma"]} for p in pages],
        }
        files["floo-project.json"] = json.dumps(manifest, indent=2).encode()
        if any((folder / name).exists() for name in files):
            raise ValueError(
                "Choose an empty project directory; existing exports are preserved."
            )
        folder.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            target = folder / name
            self._export_target(target)
            target.write_bytes(payload)
        return manifest

    def replace_texture(self, row, rows, image_path, alpha_mode):
        operation = _Operation(self)
        _, _, pages, textures = self._atlas(rows, operation)
        if row not in textures:
            raise ValueError("Select a resolved atlas page texture.")
        page = pages[textures.index(row)]
        with Image.open(image_path) as image:
            validate_image(image, page, alpha_mode)
            image = image.copy()
        return self._apply(operation, rows, [(row, image)])

    def import_spine_project(self, rows, directory, alpha_mode):
        operation = _Operation(self)
        atlas, atlas_bytes, _, textures = self._atlas(rows, operation)
        skeletons = [r for r in rows if r["role"] == "skeleton_json"]
        if len(skeletons) != 1:
            raise ValueError("Select exactly one skeleton JSON for import.")
        skeleton = skeletons[0]
        _, _, data = operation.target(skeleton)
        folder = Path(directory).resolve()

        def incoming(name):
            path = (folder / name).resolve()
            if folder not in path.parents:
                raise ValueError("Project file leaves the selected directory.")
            return path

        payload = incoming("skeleton.json").read_bytes()
        atlas_payload = incoming("skeleton.atlas").read_bytes()
        _, pages = validate_compatible(
            text_bytes(data), payload, atlas_bytes, atlas_payload
        )
        changes = [(skeleton, payload), (atlas, atlas_payload)]
        for page, row in zip(pages, textures):
            with Image.open(incoming(page["name"])) as image:
                validate_image(image, page, alpha_mode)
                changes.append((row, image.copy()))
        return self._apply(operation, rows, changes)

    @staticmethod
    def _binding_targets(bindings, qualities):
        """Expand single and multi-profile prefab bindings into physical targets."""
        targets = set()
        for quality in qualities:
            value = bindings[quality]
            targets.update(value if isinstance(value, (list, tuple)) else [value])
        return targets

    def frame_components(self, rows):
        """Convert every quality/scale profile sharing this card's animation."""
        keys = {(r["card_id"], r["asset_region"]) for r in rows}
        if len(keys) != 1 or next(iter(keys))[0] is None:
            raise ValueError("Select one monster and asset region.")
        card, region = next(iter(keys))
        return [
            r
            for r in self.rows
            if r["game_region"] == self.installation.game_region
            and r["card_id"] == card
            and r["asset_region"] == region
        ]

    def prepare_frame_animation(
        self, rows, source, options, lower_quality=False, *, allow_large_import=False
    ):
        """Generate a reviewable, bounded preview without changing game files."""
        from unity.summon_frames import decode_frames, sample_frames, preview_pngs
        from unity.summon_flipbook_graph import FlipbookGraph

        rows = self.frame_components(rows)
        operation = _Operation(self)
        profiles, duration, animation_name, quality_bindings = FlipbookGraph(
            self, operation, rows
        ).validate()
        requested = {
            p[1]["quality"]
            for p in profiles
            if not p[1].get("reference_only")
            and (p[1]["quality"] == "sd") == lower_quality
        }
        effective = self._binding_targets(quality_bindings, requested)
        selected_profiles = [p for p in profiles if p[1]["quality"] in effective]
        impacted = {
            quality
            for quality, binding in quality_bindings.items()
            if self._binding_targets(quality_bindings, [quality]) & effective
        }
        impacted.update(
            profile[1]["quality"]
            for profile in profiles
            if any(
                set(qualities) & effective
                for _, _, qualities in profile[1].get("slot_override_changes", [])
            )
        )
        shared_quality = impacted != requested
        if not selected_profiles:
            raise ValueError("The selected quality is unavailable for this card.")
        bounds = selected_profiles[0][4]["skeleton"]
        aspect = float(bounds["width"]) / float(bounds["height"])
        for profile in selected_profiles:
            box = profile[4]["skeleton"]
            if abs(float(box["width"]) / float(box["height"]) / aspect - 1) > 0.02:
                raise ValueError(
                    "Quality profiles have different framing aspect ratios."
                )
        images, delays = decode_frames(
            source, options, aspect, allow_large_import=allow_large_import
        )
        frames, indices, times = sample_frames(images, delays, duration, options)
        plan = {
            "installation": self.installation.key,
            "rows": rows,
            "options": options,
            "frames": frames,
            "indices": indices,
            "times": times,
            "duration": duration,
            "checksums": {
                str(path): checksum(payload)
                for path, (_, payload) in operation.loaded.items()
            },
            "preview": preview_pngs(frames),
            "source_duration": sum(delays),
            "animation_name": animation_name,
            "lower_quality": bool(lower_quality),
            "quality_label": (
                "Shared quality"
                if shared_quality
                else "Lower quality" if lower_quality else "High quality"
            ),
            "quality_bindings": quality_bindings,
            "selected_qualities": sorted(effective),
            "quality_warning": (
                (
                    "This card shares its animation between high and lower quality. "
                    "Replacing it affects both quality modes."
                )
                if shared_quality
                else ""
            ),
        }
        # Build now to surface capacity/encoding errors before offering Apply.
        changes = self._frame_changes(profiles, plan)
        plan["affected"] = self.affected_components([r for r, _ in changes])
        plan["summary"] = (
            f"{plan['quality_label']} · {duration:.3f} s · "
            f"{len(times)} playback frames · {len(frames)} distinct frames"
        )
        return plan

    @staticmethod
    def _frame_changes(profiles, plan):
        from unity.summon_frames import generate_quality_projects

        active_profiles = [
            p
            for p in profiles
            if p[1].get("reference_only")
            or p[1]["quality"]
            in SummonAnimationService._binding_targets(
                plan["quality_bindings"], plan["quality_bindings"]
            )
        ]
        changes = generate_quality_projects(
            active_profiles,
            plan["frames"],
            plan["indices"],
            plan["times"],
            plan["duration"],
            plan["options"],
            plan["animation_name"],
            lower_quality=plan["lower_quality"],
            selected_qualities=plan["selected_qualities"],
        )

        from unity.summon_flipbook_graph import SlotMaterialOverrides

        for profile in profiles:
            changes.extend(
                (row, SlotMaterialOverrides(tree))
                for row, tree, qualities in profile[1].get("slot_override_changes", [])
                if set(qualities) & set(plan["selected_qualities"])
            )
        return changes

    def apply_frame_animation(self, plan):
        """Revalidate preview dependencies, then use whole-bundle transactions."""
        from unity.summon_flipbook_graph import FlipbookGraph

        with _WRITE_LOCK:
            self._ensure_closed()
            if plan["installation"] != self.installation.key:
                raise ValueError("Preview belongs to a different installation.")
            rows = self.frame_components(plan["rows"])
            if rows != plan["rows"]:
                raise ValueError("Metadata changed; generate a new preview.")
            operation = _Operation(self)
            profiles, duration, animation_name, quality_bindings = FlipbookGraph(
                self, operation, rows
            ).validate()
            actual = {
                str(path): checksum(payload)
                for path, (_, payload) in operation.loaded.items()
            }
            if (
                actual != plan["checksums"]
                or duration != plan["duration"]
                or animation_name != plan["animation_name"]
                or quality_bindings != plan["quality_bindings"]
                or sorted(
                    self._binding_targets(
                        quality_bindings,
                        [
                            p[1]["quality"]
                            for p in profiles
                            if not p[1].get("reference_only")
                            and (p[1]["quality"] == "sd") == plan["lower_quality"]
                        ],
                    )
                )
                != plan["selected_qualities"]
            ):
                raise ValueError(
                    "Playback bundles changed since preview; generate a new preview."
                )
            return self._apply(operation, rows, self._frame_changes(profiles, plan))

    def _ensure_closed(self):
        if self.running():
            raise RuntimeError(
                "Close Master Duel before applying or restoring animations."
            )

    def _location(self, path):
        for source in ("local", "streaming"):
            try:
                root = self.installation.root(source)
            except ValueError:
                continue
            if root in path.resolve().parents:
                return source, path.resolve().relative_to(root).as_posix()
        raise ValueError("Bundle is outside the selected installation.")

    def _backup_keys(self, source):
        """Reuse older local-only backups after deriving the streaming root."""
        keys = [self.installation.key]
        if source == "local" and self.installation.streaming_root is not None:
            legacy = Installation(
                self.installation.game_region, self.installation.local_root
            ).key
            if legacy != keys[0]:
                keys.insert(0, legacy)
        return keys

    def _backup_path(self, source, relative, installation_key):
        key = checksum((source + "/" + relative).encode())
        return self.backups._path(
            f"summon_animations/{installation_key}/{key}/manifest.json"
        )

    def _manifest_path(self, path):
        source, relative = self._location(path)
        candidates = [
            self._backup_path(source, relative, key)
            for key in self._backup_keys(source)
        ]
        for candidate in candidates:
            if candidate.parent.exists():
                return candidate
        return self._backup_path(source, relative, self.installation.key)

    def backup_component_set(self, rows, operation=None):
        """Keep one immutable original per physical bundle across overlapping edits."""
        with _WRITE_LOCK:
            self._ensure_closed()
            operation = operation or _Operation(self)
            paths = {operation.target(row)[0] for row in rows}
            operation.dependencies(rows)
            manifests = []
            for path in sorted(paths):
                source, relative = self._location(path)
                manifest_path = self._manifest_path(path)
                if manifest_path.exists():
                    manifest = self._read_backup(manifest_path)[0]
                else:
                    payload = operation.loaded[path.resolve()][1]
                    manifest = {
                        "schema": 1,
                        "installation": self.installation.key,
                        "game_region": self.installation.game_region,
                        "source": source,
                        "relative_path": relative,
                        "sha256": checksum(payload),
                        "original_location": str(path),
                        "components": self.affected_components(
                            [r for r in rows if self.resolve(r) == path]
                        ),
                    }
                    manifest_path.parent.mkdir(parents=True, exist_ok=True)
                    original = manifest_path.parent / "original.bundle"
                    if original.exists():
                        raise ValueError(
                            "Incomplete backup exists; repair it before editing."
                        )
                    original.write_bytes(payload)
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2), encoding="utf-8"
                    )
                manifests.append(str(manifest_path))
            return manifests

    def _read_backup(self, manifest_path):
        path = Path(manifest_path).resolve()
        if self.backups.root not in path.parents:
            raise ValueError("Manifest is outside the backup directory.")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            manifest.get("schema") != 1
            or manifest.get("installation")
            not in self._backup_keys(manifest.get("source"))
            or manifest.get("game_region") != self.installation.game_region
        ):
            raise ValueError("Backup belongs to a different installation or schema.")
        destination = self.installation.path(
            manifest["source"], manifest["relative_path"]
        )
        expected = self._backup_path(
            manifest["source"], manifest["relative_path"], manifest["installation"]
        ).resolve()
        if path != expected:
            raise ValueError("Manifest location does not match its bundle identity.")
        original = path.parent / "original.bundle"
        if path.parent != original.resolve().parent:
            raise ValueError("Original backup leaves the manifest directory.")
        payload = original.read_bytes()
        if checksum(payload) != manifest["sha256"]:
            raise ValueError("Original bundle backup checksum failed.")
        return manifest, destination, payload

    @staticmethod
    def _raw_objects(env):
        return {
            (cab_name(obj.assets_file.name), str(obj.path_id)): (
                obj.data
                if getattr(obj, "data", None) is not None
                else obj.get_raw_data()
            )
            for obj in env.objects
        }

    @staticmethod
    def _resources(env):
        """Preserve every non-serialized internal bundle resource byte for byte."""
        return {
            name: resource.bytes
            for name, resource in getattr(env.file, "files", {}).items()
            if not hasattr(resource, "objects") and hasattr(resource, "bytes")
        }

    def _apply(self, operation, rows, changes):
        with _WRITE_LOCK:
            self._ensure_closed()
            operation.dependencies(rows)
            packer = (
                self.packer.lower() if isinstance(self.packer, str) else self.packer
            )
            if packer not in (None, "none", "lz4", "lzma", "original"):
                raise ValueError(
                    "Unsupported Unity compression setting; choose LZ4, LZMA or none."
                )
            originals, changed, before, resources = {}, {}, {}, {}
            for row, value in changes:
                path, obj, data = operation.target(row)
                env, original = operation.loaded[path.resolve()]
                originals[path] = original
                if path not in before:
                    before[path] = self._raw_objects(env)
                    resources[path] = self._resources(env)
                changed.setdefault(path, set()).add(
                    (cab_name(obj.assets_file.name), str(obj.path_id))
                )
                from unity.summon_flipbook_graph import SlotMaterialOverrides

                if isinstance(value, SlotMaterialOverrides):
                    if obj.type.name != "MonoBehaviour":
                        raise ValueError("Slot override target is not a component.")
                    obj.save_typetree(value.tree)
                    continue
                if isinstance(value, bytes):
                    if obj.type.name != "TextAsset":
                        raise ValueError(
                            "Only mapped TextAssets and atlas textures may be changed."
                        )
                    data.m_Script = value.decode("utf-8", "surrogateescape")
                else:
                    if obj.type.name != "Texture2D":
                        raise ValueError("Target is not a texture.")
                    stream = getattr(data, "m_StreamData", None)
                    if stream and getattr(stream, "path", ""):
                        # UnityPy embeds new pixels and clears this reference.
                        # Only a uniquely identified resource INSIDE this bundle is safe.
                        stream_path = stream.path.replace("\\", "/")
                        if "/" in stream_path and not stream_path.startswith(
                            "archive:/"
                        ):
                            raise ValueError(
                                "External texture sidecars are unsupported."
                            )
                        name = cab_name(stream.path)
                        bundled_resources = getattr(env.file, "files", {})
                        matches = [
                            resource
                            for key, resource in bundled_resources.items()
                            if cab_name(key) == name
                            and not hasattr(resource, "objects")
                        ]
                        if len(matches) != 1:
                            raise ValueError(
                                "External texture streams require an unsupported adapter."
                            )
                        resource = matches[0]
                        if (
                            not hasattr(resource, "bytes")
                            or stream.offset < 0
                            or stream.size < 0
                            or stream.offset + stream.size > len(resource.bytes)
                        ):
                            raise ValueError(
                                "Internal texture stream bounds are invalid."
                            )
                    mipmaps = getattr(data, "m_MipCount", None)
                    if mipmaps is None:
                        if getattr(data, "m_MipMap", False):
                            raise ValueError(
                                "Unknown mipmap count; cannot preserve policy safely."
                            )
                        mipmaps = 1
                    flags = (data.m_TextureFormat, mipmaps)
                    from unity.summon_frames import AtlasSheet

                    image = value.render() if isinstance(value, AtlasSheet) else value
                    try:
                        data.set_image(
                            image, target_format=flags[0], mipmap_count=flags[1]
                        )
                    finally:
                        if isinstance(value, AtlasSheet):
                            image.close()
                    if getattr(getattr(data, "m_StreamData", None), "path", ""):
                        raise ValueError("Texture encoder retained a stream reference.")
                    if (
                        data.m_TextureFormat,
                        (getattr(data, "m_MipCount", None) or 1),
                    ) != flags:
                        raise ValueError(
                            "Texture encoder changed format/mipmap policy; edit refused."
                        )
                data.save()
            outputs = {}
            for path in originals:
                env = operation.loaded[path.resolve()][0]
                payload = env.file.save(packer=packer)
                reloaded = self.loader(payload)
                if self._resources(reloaded) != resources[path]:
                    raise ValueError("Save changed an internal bundle resource.")
                actual = self._raw_objects(reloaded)
                expected = self._raw_objects(env)
                if actual != expected:
                    raise ValueError("Saved bundle objects failed byte verification.")
                for key, raw in before[path].items():
                    if key not in changed[path] and actual.get(key) != raw:
                        raise ValueError("Save changed an unrelated Unity object.")
                for row, _ in changes:
                    if self.resolve(row) == path:
                        operation.target(row, reloaded)
                outputs[path] = payload
            manifests = self.backup_component_set(
                [row for row, _ in changes], operation
            )
            self._commit(outputs, originals)
            return {
                "manifests": manifests,
                "modified": True,
                "affected": self.affected_components([r for r, _ in changes]),
            }

    def backup_inventory(self):
        """Inspect originals, including verified local-only backups from earlier UI."""
        entries, seen = [], set()
        keys = self._backup_keys("local")
        for key in keys:
            root = self.backups._path(f"summon_animations/{key}")
            for path in sorted(root.glob("*/manifest.json")):
                if path.parent.name in seen:
                    continue
                seen.add(path.parent.name)
                try:
                    manifest, _, _ = self._read_backup(path)
                    entries.append({"path": str(path), "manifest": manifest})
                except (ValueError, OSError) as error:
                    entries.append({"path": str(path), "error": str(error)})
        return entries

    def restore_component_set(self, rows=None, manifests=None):
        """Restore full original bytes, including every component in shared bundles."""
        with _WRITE_LOCK:
            self._ensure_closed()
            if manifests is None:
                manifests = [
                    self._manifest_path(path)
                    for path in {self.resolve(r) for r in rows}
                ]
            outputs, originals, affected = {}, {}, []
            for manifest_path in dict.fromkeys(map(str, manifests)):
                manifest, path, payload = self._read_backup(manifest_path)
                # Restoration intentionally does not depend on current remote metadata.
                self.loader(payload)
                outputs[path] = payload
                originals[path] = path.read_bytes()
                affected.extend(manifest["components"])
            if not outputs:
                raise ValueError("No complete bundle backups selected.")
            self._commit(outputs, originals)
            return {
                "manifests": list(map(str, manifests)),
                "modified": False,
                "affected": affected,
            }

    def _commit(self, outputs, originals):
        """Stage on destination volumes, then atomically replace with rollback."""
        stages, replaced = {}, []
        try:
            for path, payload in outputs.items():
                source, relative = self._location(path)
                self.installation.path(source, relative)
                with NamedTemporaryFile(dir=path.parent, delete=False) as file:
                    stage = Path(file.name)
                    stages[path] = stage
                    file.write(payload)
                    file.flush()
                    os.fsync(file.fileno())
                if stage.read_bytes() != payload:
                    raise OSError("Staged bundle checksum failed.")
                self.loader(stage.read_bytes())
            self._ensure_closed()
            for path in outputs:
                if path.read_bytes() != originals[path]:
                    raise RuntimeError(
                        "Bundle changed during preparation; retry after closing other editors."
                    )
            for path, stage in stages.items():
                os.replace(stage, path)
                replaced.append(path)
                if path.read_bytes() != outputs[path]:
                    raise OSError("Destination checksum failed.")
        except Exception:
            failures = []
            for path in reversed(replaced):
                try:
                    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
                        rollback = Path(file.name)
                        file.write(originals[path])
                        file.flush()
                        os.fsync(file.fileno())
                    try:
                        os.replace(rollback, path)
                    finally:
                        rollback.unlink(missing_ok=True)
                except OSError as error:
                    failures.append(f"{path}: {error}")
            if failures:
                raise RuntimeError(
                    "Rollback failed; restore original bundle backups: "
                    + "; ".join(failures)
                )
            raise
        finally:
            for stage in stages.values():
                stage.unlink(missing_ok=True)
