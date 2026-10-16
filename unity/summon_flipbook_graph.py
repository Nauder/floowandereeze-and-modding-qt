"""Conservative adapter for cut-ins driven by synchronized Spine timeline clips."""

import math
import json
from copy import deepcopy
from dataclasses import dataclass

from unity.summon_metadata import validate_row

from unity.summon_spine import text_bytes, validate_spine


@dataclass
class SlotMaterialOverrides:
    """A validated reset of cross-profile overrides, saved in the bundle transaction."""

    tree: dict


class FlipbookGraph:
    """Resolve Unity pointers using actual CAB dependencies, never asset names."""

    def __init__(self, service, operation, rows):
        self.service, self.operation, self.rows = service, operation, rows
        operation.dependencies(rows)
        self.objects = {}
        self.validated_timeline_components = set()
        for env, _ in operation.loaded.values():
            for obj in env.objects:
                key = self.key(obj)
                if key in self.objects and self.objects[key] is not obj:
                    raise ValueError("Ambiguous Unity object in playback dependencies.")
                self.objects[key] = obj

    def object_row(self, obj, role, quality=None):
        """Register an exact object reached through a validated playback pointer."""
        for row in self.rows:
            if row["role"] == role and self.key(
                self.operation.target(row)[1]
            ) == self.key(obj):
                return dict(row)
        matches = []
        for row in self.rows:
            path = self.service.resolve(row).resolve()
            env = self.operation.loaded[path][0]
            if any(candidate is obj for candidate in env.objects):
                matches.append(row)
        if not matches:
            raise ValueError("Embedded playback object is outside this card's bundles.")
        row = dict(matches[0])
        data = obj.read()
        row.update(
            role=role,
            quality=quality,
            path_id=str(obj.path_id),
            serialized_file=str(obj.assets_file.name),
            object_type=obj.type.name,
            asset_name=getattr(data, "m_Name", ""),
            external_references=json.dumps([p.path for p in obj.assets_file.externals]),
        )
        if role == "skeleton_json":
            project = json.loads(text_bytes(data))
            row.update(
                spine_version=project["skeleton"]["spine"],
                animation_names=json.dumps(sorted(project["animations"])),
            )
        self.operation.discovered[self.operation.discovery_key(row)] = validate_row(row)
        return row

    def profile_rows(self):
        """Resolve duplicate JSON exports by the prefab's actual SkeletonDataAsset."""
        rows = [dict(row) for row in self.rows]
        for quality in {r["quality"] for r in rows if r["role"] == "skeleton_data"}:
            candidates = [
                r
                for r in rows
                if r["role"] == "skeleton_data" and r["quality"] == quality
            ]
            if len(candidates) <= 1:
                continue
            bindings = set()
            for prefab in rows:
                if prefab["role"] != "prefab" or prefab["quality"] != quality:
                    continue
                env = self.operation.load_path(self.service.resolve(prefab))
                for obj in env.objects:
                    if obj.type.name == "MonoBehaviour":
                        cls, ns, tree = self.script(obj)
                        if (ns, cls) == (
                            "Spine.Unity",
                            "SkeletonAnimation",
                        ) and tree.get("skeletonDataAsset", {}).get("m_PathID"):
                            bindings.add(
                                self.key(self.pointer(obj, tree["skeletonDataAsset"]))
                            )
            selected = [
                r
                for r in candidates
                if self.key(self.operation.target(r)[1]) in bindings
            ]
            if len(selected) != 1:
                raise ValueError(
                    "Duplicate skeleton profiles do not have one verified renderer binding."
                )
            data_obj = self.operation.target(selected[0])[1]
            json_key = self.key(
                self.pointer(data_obj, data_obj.read_typetree()["skeletonJSON"])
            )
            rows = [
                r
                for r in rows
                if r["quality"] != quality
                or r["role"] not in {"skeleton_data", "skeleton_json"}
                or (r["role"] == "skeleton_data" and r == selected[0])
                or (
                    r["role"] == "skeleton_json"
                    and self.key(self.operation.target(r)[1]) == json_key
                )
            ]
        return rows

    @staticmethod
    def key(obj):
        return str(obj.assets_file.name).replace("\\", "/").rsplit("/", 1)[
            -1
        ].casefold(), int(obj.path_id)

    def pointer(self, origin, pointer):
        file_id, path_id = pointer["m_FileID"], pointer["m_PathID"]
        if not path_id:
            raise ValueError("Required playback pointer is null.")
        if not 0 <= file_id <= len(origin.assets_file.externals):
            raise ValueError("Invalid playback dependency index.")
        name = (
            origin.assets_file.name
            if file_id == 0
            else origin.assets_file.externals[file_id - 1].path
        )
        key = str(name).replace("\\", "/").rsplit("/", 1)[-1].casefold(), int(path_id)
        if key not in self.objects:
            raise ValueError("Playback dependency object is missing.")
        return self.objects[key]

    def script(self, obj):
        if obj.type.name != "MonoBehaviour":
            raise ValueError("Expected a serialized playback component.")
        tree = obj.read_typetree()
        script = self.pointer(obj, tree["m_Script"])
        if script.type.name != "MonoScript":
            raise ValueError("Playback script pointer has changed.")
        data = script.read_typetree()
        return data["m_ClassName"], data["m_Namespace"], tree

    def target(self, role, rows=None):
        candidates = [
            r for r in (self.rows if rows is None else rows) if r["role"] == role
        ]
        if role == "timeline":
            return self.timeline_target(candidates)
        if len(candidates) != 1:
            raise ValueError(
                f"Animation replacement requires exactly one {role} for the selected profile."
            )
        row = candidates[0]
        _, obj, _ = self.operation.target(row)
        return row, obj

    def timeline_target(self, rows):
        """Resolve a playable root when metadata also names curve sub-assets."""
        roots = self.timeline_targets(rows)
        if len(roots) != 1:
            raise ValueError(
                "Animation replacement requires exactly one timeline root."
            )
        return roots[0]

    def timeline_targets(self, rows):
        """Resolve every recorded timeline variant without guessing from its name."""
        roots = {}
        for row in rows:
            path, recorded, _ = self.operation.target(row)
            env = self.operation.load_path(path)
            row_roots = {}
            for name, pointer in env.container.items():
                if name != row["asset_path"]:
                    continue
                obj = pointer.deref()
                if (
                    obj.type.name != "MonoBehaviour"
                    or self.key(obj)[0] != self.key(recorded)[0]
                ):
                    continue
                cls, namespace, _ = self.script(obj)
                if (namespace, cls) == ("UnityEngine.Timeline", "TimelineAsset"):
                    row_roots[self.key(obj)] = (row, obj)
            if len(row_roots) > 1:
                raise ValueError(
                    "Animation replacement requires exactly one timeline root per metadata path."
                )
            roots.update(row_roots)
        if not roots:
            raise ValueError("No verified timeline root is available.")
        return list(roots.values())

    def wrapper(self, role, cls, rows):
        row, obj = self.target(role, rows)
        actual, namespace, tree = self.script(obj)
        if actual != cls or namespace != "Spine.Unity":
            raise ValueError(f"Unsupported {role} script: {namespace}.{actual}.")
        return row, obj, tree

    def same(self, origin, pointer, target):
        if self.key(self.pointer(origin, pointer)) != self.key(target):
            raise ValueError("Playback pointer does not match selected metadata.")

    def effect_clip(self, obj):
        """Retain numeric material, root transform and sprite-color curves."""
        if obj.type.name != "AnimationClip":
            raise ValueError(
                "Auxiliary timeline asset does not select an AnimationClip."
            )
        tree = obj.read_typetree()
        bindings = tree.get("m_ClipBindingConstant", {})
        if any(
            tree.get(key)
            for key in (
                "m_Events",
                "m_PPtrCurves",
                "m_CompressedRotationCurves",
                "m_HasMotionFloatCurves",
            )
        ) or bindings.get("pptrCurveMapping"):
            raise ValueError(
                "Auxiliary animation must contain only numeric material curves."
            )
        for binding in bindings.get("genericBindings", []):
            if (
                not (
                    (binding.get("typeID"), binding.get("customType")) == (23, 22)
                    or (
                        binding.get("typeID") == 4
                        and binding.get("customType") == 0
                        and binding.get("path") == 0
                        and binding.get("attribute") in {1, 2, 3, 4}
                    )
                    or (
                        binding.get("typeID") == 212
                        and binding.get("customType") == 0
                        and binding.get("path") == 0
                        and binding.get("attribute")
                        in {304273561, 2526845255, 4215373228, 2334886179}
                    )
                )
                or binding.get("script", {}).get("m_PathID")
                or binding.get("isPPtrCurve")
                or binding.get("isSerializeReferenceCurve")
            ):
                raise ValueError(
                    "Auxiliary animation has unsupported renderer/script bindings."
                )
        if tree.get("m_HasGenericRootTransform") and not any(
            b.get("typeID") == 4 for b in bindings.get("genericBindings", [])
        ):
            raise ValueError("Auxiliary animation has unverified root motion.")
        for kind in (
            "m_RotationCurves",
            "m_EulerCurves",
            "m_PositionCurves",
            "m_ScaleCurves",
        ):
            if any(curve.get("path") != "" for curve in tree.get(kind, [])):
                raise ValueError("Auxiliary animation has non-root transform curves.")
        for curve in tree.get("m_FloatCurves", []):
            if not (
                (
                    curve.get("classID") == 23
                    and (curve.get("attribute") or "").startswith("material.")
                )
                or (
                    curve.get("classID") == 212
                    and curve.get("path") == ""
                    and curve.get("attribute")
                    in {"m_Color.r", "m_Color.g", "m_Color.b", "m_Color.a"}
                )
            ) or curve.get("script", {}).get("m_PathID"):
                raise ValueError(
                    "Auxiliary animation has unsupported non-material curves."
                )

    def effect_material_pma(self, material, tree):
        """Recognize the game's straight-alpha fog/fire atlas shaders."""
        shader = self.pointer(material, tree["m_Shader"])
        if shader.type.name != "Shader":
            raise ValueError("Atlas material shader pointer is invalid.")
        parsed = shader.read_typetree().get("m_ParsedForm", {})
        if parsed.get("m_Name") not in {
            "TimelineShader/SM/SM_FogShader",
            "TimelineShader/SM/SM_FogLight_Shader",
            "TimelineShader/SM/SM_Fire2_Shader",
            "TimelineShader/SM/SM_Fire_Shader",
            "TimelineShader/SM/SM_Shake_Shader",
            "TimelineShader/SM/SM_P13199",
        }:
            raise ValueError("Atlas/material alpha mode is unspecified.")
        states = [
            p.get("m_State", {})
            for sub in parsed.get("m_SubShaders", [])
            for p in sub.get("m_Passes", [])
            if p.get("m_State", {}).get("m_Name") == "Universal Forward"
        ]
        # Unity BlendMode: SrcAlpha=5, OneMinusSrcAlpha=10; BlendOp Add=0.
        # Verify the compiled color pass rather than assume settings by name.
        if not states:
            raise ValueError("Effect shader has no verified color pass.")
        for state in states:
            blend = state.get("rtBlend0", {})
            for field, expected in (("srcBlend", 5), ("destBlend", 10), ("blendOp", 0)):
                value = blend.get(field, {})
                if value.get("val") != expected or value.get("name") not in (
                    "",
                    "<noninit>",
                ):
                    raise ValueError("Effect shader alpha blending is unsupported.")
        return False

    def custom_materials(self, obj, tree, renderer, profile):
        """Validate legacy-slot overrides while keeping their components/materials intact."""
        if not tree.get("m_Enabled", 1):
            return
        self.same(obj, tree["skeletonRenderer"], renderer)
        original = profile[4]
        slots = {slot["name"] for slot in original.get("slots", [])}
        textures = {self.key(self.operation.target(row)[1]) for row in profile[3]}
        for override in tree.get("customMaterialOverrides", []):
            if not override.get("overrideDisabled"):
                raise ValueError(
                    "Active whole-skeleton material overrides are unsupported."
                )
        seen = {}
        replacement = deepcopy(tree)
        reset_indices = []
        reset_qualities = {profile[1]["quality"]}
        for override_index, override in enumerate(tree.get("customSlotMaterials", [])):
            if override.get("overrideDisabled"):
                continue
            name = override.get("slotName")
            pointer = override.get("material", {})
            # Unity serializes empty inspector rows; these bind no slot/material.
            if not name and not pointer.get("m_PathID"):
                continue
            if name not in slots or name.startswith("floo_frames_"):
                raise ValueError(
                    "Custom material override does not select a unique legacy slot."
                )
            material = self.pointer(obj, pointer)
            identity = self.key(material)
            if name in seen and seen[name] != identity:
                raise ValueError("Conflicting custom material overrides for one slot.")
            seen[name] = identity
            if material.type.name != "Material":
                raise ValueError("Custom slot override must select a Material.")
            props = material.read_typetree()["m_SavedProperties"]
            main = [value for key, value in props["m_TexEnvs"] if key == "_MainTex"]
            if len(main) != 1:
                raise ValueError(
                    "Custom slot material does not use the renderer's atlas textures."
                )
            texture_key = self.key(self.pointer(material, main[0]["m_Texture"]))
            if texture_key not in textures:
                verified = {
                    self.key(self.operation.target(row)[1])
                    for row in self.rows
                    if row["role"] == "texture"
                }
                if texture_key not in verified:
                    raise ValueError(
                        "Custom slot material does not use the renderer's atlas textures."
                    )
                reset_indices.append(override_index)
                reset_qualities.update(
                    row["quality"]
                    for row in self.rows
                    if row["role"] == "texture"
                    and self.key(self.operation.target(row)[1]) == texture_key
                )
            if main[0].get("m_Scale", {"x": 1, "y": 1}) != {"x": 1, "y": 1} or main[
                0
            ].get("m_Offset", {"x": 0, "y": 0}) != {"x": 0, "y": 0}:
                raise ValueError(
                    "Custom slot material texture offsets are unsupported."
                )

        if reset_indices:
            for index in reset_indices:
                replacement["customSlotMaterials"][index]["overrideDisabled"] = 1
            row = self.object_row(obj, "other", profile[1]["quality"])
            profile[1].setdefault("slot_override_changes", []).append(
                (row, replacement, sorted(q for q in reset_qualities if q))
            )

    def playback(self):
        """Follow the timeline clip to its actual Spine reference, retaining effect tracks."""
        timeline_rows = [r for r in self.rows if r["role"] == "timeline"]
        roots = self.timeline_targets(timeline_rows) if timeline_rows else []
        for prefab in [r for r in self.rows if r["role"] == "prefab"]:
            env = self.operation.load_path(self.service.resolve(prefab))
            for obj in env.objects:
                if obj.type.name == "MonoBehaviour" and self.script(obj)[:2] == (
                    "TimelineAsset",
                    "UnityEngine.Timeline",
                ):
                    if self.key(obj) not in {self.key(root) for _, root in roots}:
                        roots.append((prefab, obj))
        references, durations = {}, []
        for row, root in roots:
            refs, duration = self.playback_timeline(row, root)
            references.update((self.key(ref), (ref, tree)) for ref, tree in refs)
            if duration is not None:
                durations.append(duration)
        if not references or not durations:
            raise ValueError("Timeline has no Spine animation clips.")
        if any(
            not math.isclose(value, durations[0], rel_tol=0, abs_tol=1e-6)
            for value in durations
        ):
            raise ValueError("Timeline variants must have the same bounded duration.")
        if len({tree["animationName"] for _, tree in references.values()}) != 1:
            raise ValueError("Timeline variants must select the same animation name.")
        self.playback_references = list(references.values())
        reference, tree = self.playback_references[0]
        return reference, tree, durations[0]

    def playback_timeline(self, timeline_row, timeline):
        """Validate one complete timeline and retain all its animation references."""
        env = self.operation.load_path(self.service.resolve(timeline_row))
        clips = []
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            cls, namespace, tree = self.script(obj)
            if (namespace, cls) in {
                ("Spine.Unity", "SkeletonDataAsset"),
                ("Spine.Unity", "SpineAtlasAsset"),
                ("Spine.Unity", "AnimationReferenceAsset"),
                ("Spine.Unity", "SkeletonAnimation"),
                ("Spine.Unity", "SkeletonRendererCustomMaterials"),
                ("YgomSystem.ElementSystem", "ElementObjectManager"),
                ("YgomSystem.Effect", "ScreenEffect"),
            }:
                continue
            expected_namespace = (
                "Spine.Unity.Playables"
                if cls.startswith("SpineAnimationState")
                else "UnityEngine.Timeline"
            )
            if namespace != expected_namespace:
                raise ValueError("Unsupported timeline script namespace.")
            if (
                tree.get("m_Curves", {}).get("m_PathID")
                or tree.get("m_AnimClip", {}).get("m_PathID")
                or tree.get("m_Markers", {}).get("m_Objects")
            ):
                raise ValueError(
                    "Timeline curves, animation bindings or markers are unsupported."
                )
            if cls not in {
                "TimelineAsset",
                "GroupTrack",
                "SpineAnimationStateTrack",
                "SpineAnimationStateClip",
                "MarkerTrack",
                "AnimationTrack",
                "AnimationPlayableAsset",
            }:
                raise ValueError(f"Unsupported timeline component: {cls}.")
            self.validated_timeline_components.add(self.key(obj))
            if cls == "AnimationPlayableAsset":
                self.effect_clip(self.pointer(obj, tree["m_Clip"]))
            if cls == "AnimationTrack" and (
                tree.get("m_AvatarMask", {}).get("m_PathID")
                or tree.get("m_CustomPlayableFullTypename")
            ):
                raise ValueError(
                    "Custom or masked auxiliary animation tracks are unsupported."
                )
            if cls == "AnimationTrack":
                if tree.get("m_InfiniteClip", {}).get("m_PathID"):
                    self.effect_clip(self.pointer(obj, tree["m_InfiniteClip"]))
                for auxiliary in tree.get("m_Clips", []):
                    if auxiliary.get("m_AnimationCurves", {}).get(
                        "m_PathID"
                    ) or auxiliary.get("m_ExposedParameterNames"):
                        raise ValueError(
                            "Auxiliary clip curves or exposed bindings are unsupported."
                        )
                    asset = self.pointer(obj, auxiliary["m_Asset"])
                    asset_class, asset_namespace, asset_tree = self.script(asset)
                    if (asset_namespace, asset_class) != (
                        "UnityEngine.Timeline",
                        "AnimationPlayableAsset",
                    ):
                        raise ValueError(
                            "Auxiliary track must select an AnimationPlayableAsset."
                        )
                    self.effect_clip(self.pointer(asset, asset_tree["m_Clip"]))
            if cls == "SpineAnimationStateTrack":
                clips.extend((obj, clip) for clip in tree["m_Clips"])
        root_class, _, root_tree = self.script(timeline)
        if root_class != "TimelineAsset":
            raise ValueError(
                "Timeline metadata does not select the root TimelineAsset."
            )
        reachable = set()
        pending = [self.pointer(timeline, p) for p in root_tree["m_Tracks"]]
        marker = root_tree.get("m_MarkerTrack", {})
        if marker.get("m_PathID"):
            obj = self.pointer(timeline, marker)
            cls, namespace, tree = self.script(obj)
            if (namespace, cls) != ("UnityEngine.Timeline", "MarkerTrack") or tree.get(
                "m_Markers", {}
            ).get("m_Objects"):
                raise ValueError("Timeline marker bindings are unsupported.")
        while pending:
            obj = pending.pop()
            if self.key(obj) in reachable:
                raise ValueError("Timeline track graph is cyclic or duplicated.")
            reachable.add(self.key(obj))
            child_class, child_namespace, tree = self.script(obj)
            expected = (
                "Spine.Unity.Playables"
                if child_class == "SpineAnimationStateTrack"
                else "UnityEngine.Timeline"
            )
            if child_namespace != expected or child_class not in {
                "GroupTrack",
                "SpineAnimationStateTrack",
                "AnimationTrack",
                "MarkerTrack",
            }:
                raise ValueError("Timeline references an unsupported track.")
            pending.extend(self.pointer(obj, p) for p in tree.get("m_Children", []))
        tracks = {}
        references = {}
        for track, clip in clips:
            if self.key(track) not in reachable:
                raise ValueError("Spine track is not connected to the root timeline.")
            reference, tree, start, duration = self.playback_clip(track, clip)
            references[self.key(reference)] = (reference, tree)
            tracks.setdefault(self.key(track), []).append(
                (start, duration, self.key(reference))
            )
        if not tracks:
            return [], None
        spans = []
        for segments in tracks.values():
            end = 0.0
            reference_key = segments[0][2]
            for start, duration, key in sorted(segments):
                if not math.isclose(start, end, rel_tol=0, abs_tol=1e-6):
                    raise ValueError(
                        "Spine clips must form a continuous timeline without gaps or overlaps."
                    )
                if key != reference_key:
                    raise ValueError(
                        "Sequential Spine clips must use the same animation reference."
                    )
                end = start + duration
            spans.append(end)
        if not 0 < spans[0] <= 10 or any(
            not math.isclose(span, spans[0], rel_tol=0, abs_tol=1e-6) for span in spans
        ):
            raise ValueError(
                "Parallel Spine tracks must have the same bounded duration."
            )
        if len({tree["animationName"] for _, tree in references.values()}) != 1:
            raise ValueError(
                "Parallel Spine tracks must select the same animation name."
            )
        return list(references.values()), spans[0]

    def playback_clip(self, track, clip):
        """Validate a continuous segment in the shared animation time domain."""
        start = float(clip["m_Start"])
        if (
            not math.isfinite(start)
            or start < 0
            or not math.isclose(float(clip["m_ClipIn"]), start, rel_tol=0, abs_tol=1e-6)
            or clip["m_TimeScale"] != 1
        ):
            raise ValueError("Offset or retimed clips are unsupported.")
        if clip.get("m_AnimationCurves", {}).get("m_PathID") or clip.get(
            "m_ExposedParameterNames"
        ):
            raise ValueError("Clip curves or exposed bindings are unsupported.")
        clip_obj = self.pointer(track, clip["m_Asset"])
        cls, namespace, tree = self.script(clip_obj)
        if (namespace, cls) != ("Spine.Unity.Playables", "SpineAnimationStateClip"):
            raise ValueError("Timeline does not point to a Spine clip.")
        template = tree["template"]
        reference = self.pointer(clip_obj, template["animationReference"])
        reference_class, reference_namespace, ref_tree = self.script(reference)
        if (reference_namespace, reference_class) != (
            "Spine.Unity",
            "AnimationReferenceAsset",
        ):
            raise ValueError("Timeline does not select a Spine animation reference.")
        # Legacy customDuration selects mixing settings, not clip retiming.
        if template.get("loop") or template.get("dontEndWithClip"):
            raise ValueError("Looping or open-ended clips are unsupported.")
        duration = float(clip["m_Duration"])
        if not math.isfinite(duration) or not 0 < duration <= 10:
            raise ValueError("Unsupported timeline duration.")
        return reference, ref_tree, start, duration

    def prefab_renderer(self, prefab):
        """Validate each prefab variant and retain its renderer/override context."""
        path, _, _ = self.operation.target(prefab)
        env = self.operation.load_path(path)
        custom_materials = []
        binding = None
        components = []
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            cls, namespace, tree = self.script(obj)
            if (namespace, cls) == ("Spine.Unity", "SkeletonAnimation"):
                # Empty helper renderers cannot initialize a Spine skeleton.
                # Keep them intact, but select the one with an actual binding.
                if not tree.get("skeletonDataAsset", {}).get("m_PathID"):
                    if tree.get("_animationName"):
                        raise ValueError("Unbound renderer requests an animation.")
                    continue
                components.append(obj)
                binding = self.key(self.pointer(obj, tree["skeletonDataAsset"]))
                if (
                    tree.get("separatorSlotNames")
                    or tree.get("initialSkinName") not in ("", "default")
                    or tree.get("singleSubmesh")
                    or tree.get("immutableTriangles")
                ):
                    raise ValueError(
                        "Unsupported prefab skin, separator or mesh policy."
                    )
            elif (namespace, cls) == (
                "Spine.Unity",
                "SkeletonRendererCustomMaterials",
            ):
                custom_materials.append((obj, tree))
            elif (namespace, cls) == (
                "YgomSystem.ElementSystem",
                "ElementObjectManager",
            ):
                if tree.get("serializedElements"):
                    raise ValueError(
                        "Prefab has unvalidated external element bindings."
                    )
            elif (namespace, cls) in {
                ("UnityEngine.Timeline", "TimelineAsset"),
                ("UnityEngine.Timeline", "AnimationTrack"),
                ("UnityEngine.Timeline", "AnimationPlayableAsset"),
                ("UnityEngine.Timeline", "MarkerTrack"),
                ("UnityEngine.Timeline", "GroupTrack"),
                ("Spine.Unity.Playables", "SpineAnimationStateTrack"),
                ("Spine.Unity.Playables", "SpineAnimationStateClip"),
                ("Spine.Unity", "SkeletonDataAsset"),
                ("Spine.Unity", "SpineAtlasAsset"),
                ("Spine.Unity", "AnimationReferenceAsset"),
            }:
                if (
                    namespace in {"UnityEngine.Timeline", "Spine.Unity.Playables"}
                    and self.key(obj) not in self.validated_timeline_components
                ):
                    raise ValueError(
                        "Prefab has an unvalidated embedded timeline component."
                    )
                continue
            elif (namespace, cls) != ("YgomSystem.Effect", "ScreenEffect"):
                raise ValueError(f"Unsupported prefab component: {namespace}.{cls}.")
        if len(components) != 1:
            raise ValueError("Prefab must contain exactly one SkeletonAnimation.")
        return components[0], binding, custom_materials

    def reference_profile(self, data_obj, name, index, fallback_pages):
        """Extend an embedded animation source without changing its atlas or renderers."""
        cls, ns, tree = self.script(data_obj)
        if (ns, cls) != ("Spine.Unity", "SkeletonDataAsset"):
            raise ValueError(
                "Shared animation reference does not match converted profiles."
            )
        if (
            tree.get("skeletonDataModifiers")
            or tree.get("controller", {}).get("m_PathID")
            or tree.get("fromAnimation")
            or tree.get("toAnimation")
        ):
            raise ValueError(
                "Embedded skeleton modifiers and custom mixes are unsupported."
            )
        obj = self.pointer(data_obj, tree["skeletonJSON"])
        if obj.type.name != "TextAsset":
            raise ValueError("Embedded skeleton JSON is not a TextAsset.")
        project = json.loads(text_bytes(obj.read()))
        version = project["skeleton"]["spine"]
        validate_spine(text_bytes(obj.read()), version)
        if not version.startswith("4.2.") or name not in project["animations"]:
            raise ValueError(
                "Embedded skeleton has an unsupported version or animation."
            )
        quality = f"reference_{index}"
        row = self.object_row(obj, "skeleton_json", quality)
        row = dict(row, quality=quality, reference_only=True)
        # Internal rows retain their original identity in the operation registry.
        if self.operation.discovery_key(row) in self.operation.discovered:
            self.operation.discovered[self.operation.discovery_key(row)] = validate_row(
                row
            )
        pages = fallback_pages
        atlases = tree.get("atlasAssets", [])
        if len(atlases) == 1 and atlases[0].get("m_PathID"):
            atlas_obj = self.pointer(data_obj, atlases[0])
            actual, namespace, atlas_tree = self.script(atlas_obj)
            if (namespace, actual) != ("Spine.Unity", "SpineAtlasAsset"):
                raise ValueError("Embedded atlas pointer is invalid.")
            from unity.summon_spine import parse_atlas

            atlas_file = self.pointer(atlas_obj, atlas_tree["atlasFile"])
            pages = parse_atlas(text_bytes(atlas_file.read()))
        return ([], row, None, [], project, pages)

    def validate(self):
        """Return profiles, clip duration and the animation selected by the timeline."""
        profile_rows = self.profile_rows()
        skeleton_rows = [r for r in profile_rows if r["role"] == "skeleton_json"]
        if not skeleton_rows:
            raise ValueError("No skeleton profiles are available.")
        reference, ref_tree, duration = self.playback()
        name = ref_tree["animationName"]
        profiles, data_assets, animation_sets = [], [], []
        renderer_bindings = {}
        custom_materials = []
        for skeleton in skeleton_rows:
            rows = [r for r in profile_rows if r["quality"] == skeleton["quality"]]
            _, skel_obj = self.target("skeleton_json", rows)
            original = validate_spine(
                text_bytes(skel_obj.read()), skeleton["spine_version"]
            )
            version = original["skeleton"]["spine"]
            if not version.startswith("4.2."):
                raise ValueError(
                    f"Unsupported Spine version {version} in {skeleton['quality']} profile; "
                    "flipbook import currently supports Spine 4.2."
                )
            if name not in original["animations"]:
                available = ", ".join(sorted(original["animations"])) or "(none)"
                raise ValueError(
                    f"Timeline animation {name!r} is missing from {skeleton['quality']} "
                    f"skeleton. Available animations: {available}. Refresh metadata."
                )
            bounds = original["skeleton"]
            if (
                any(
                    not math.isfinite(float(bounds.get(k, 0)))
                    for k in ("x", "y", "width", "height")
                )
                or min(float(bounds.get("width", 0)), float(bounds.get("height", 0)))
                <= 0
            ):
                raise ValueError("Missing or invalid skeleton framing bounds.")
            animation_sets.append(set(original["animations"]))
            atlas, atlas_payload, pages, textures = self.service._atlas(
                rows, self.operation, allow_resized=True
            )
            _, atlas_obj, _ = self.operation.target(atlas)
            _, data_obj, data = self.wrapper("skeleton_data", "SkeletonDataAsset", rows)
            self.same(data_obj, data["skeletonJSON"], skel_obj)
            _, atlas_asset, atlas_tree = self.wrapper(
                "atlas_asset", "SpineAtlasAsset", rows
            )
            if len(data["atlasAssets"]) != 1:
                raise ValueError("Multiple atlas assets are unsupported.")
            self.same(data_obj, data["atlasAssets"][0], atlas_asset)
            self.same(atlas_asset, atlas_tree["atlasFile"], atlas_obj)
            if (
                data.get("skeletonDataModifiers")
                or data.get("controller", {}).get("m_PathID")
                or data.get("fromAnimation")
                or data.get("toAnimation")
            ):
                raise ValueError(
                    "Skeleton modifiers, controllers and custom mixes are unsupported."
                )
            blend = data.get("blendModeMaterials", {})
            if any(
                blend.get(k)
                for k in ("additiveMaterials", "multiplyMaterials", "screenMaterials")
            ):
                raise ValueError("Extra blend-mode materials are unsupported.")
            if atlas_tree.get("textureLoadingMode", 0) != 0 or atlas_tree.get(
                "onDemandTextureLoader", {}
            ).get("m_PathID"):
                raise ValueError("On-demand atlas loading is unsupported.")
            materials = atlas_tree["materials"]
            if len(materials) != len(textures):
                raise ValueError("Atlas material/page count differs.")
            for pointer, texture, page in zip(materials, textures, pages):
                material = self.pointer(atlas_asset, pointer)
                if material.type.name != "Material":
                    raise ValueError("Atlas material pointer is invalid.")
                tree = material.read_typetree()
                props = tree["m_SavedProperties"]
                tex = [v for k, v in props["m_TexEnvs"] if k == "_MainTex"]
                if len(tex) != 1:
                    raise ValueError("Material does not have one main texture.")
                _, tex_obj, _ = self.operation.target(texture)
                self.same(material, tex[0]["m_Texture"], tex_obj)
                floats = dict(props["m_Floats"])
                lines = [line.strip() for line in atlas_payload.decode().splitlines()]
                start = lines.index(page["name"]) + 1
                headers = []
                for line in lines[start:]:
                    if ":" not in line:
                        break
                    headers.append(line.split(":", 1)[0])
                if "_StraightAlphaInput" in floats:
                    material_pma = not bool(floats["_StraightAlphaInput"])
                    if "pma" in headers and material_pma != page["pma"]:
                        raise ValueError("Material and atlas alpha modes disagree.")
                    page["pma"] = material_pma
                elif "pma" not in headers:
                    page["pma"] = self.effect_material_pma(material, tree)
            prefabs = [r for r in rows if r["role"] == "prefab"]
            if not prefabs:
                raise ValueError("No prefab is available for this skeleton profile.")
            for prefab in prefabs:
                renderer, binding, overrides = self.prefab_renderer(prefab)
                quality = skeleton["quality"]
                renderer_bindings.setdefault(quality, set()).add(binding)
                custom_materials.extend(
                    (quality, renderer, binding, obj, tree) for obj, tree in overrides
                )
            data_assets.append(self.key(data_obj))
            profiles.append((rows, skeleton, atlas, textures, original, pages))
        if any(names != animation_sets[0] for names in animation_sets):
            raise ValueError("Profiles use different animation names.")
        reference_profiles = []
        known_json = {self.key(self.operation.target(p[1])[1]) for p in profiles}
        for ref, tree in self.playback_references:
            data_obj = self.pointer(ref, tree["skeletonDataAsset"])
            if self.key(data_obj) in data_assets:
                continue
            profile = self.reference_profile(
                data_obj, name, len(reference_profiles), profiles[0][5]
            )
            json_key = self.key(self.operation.target(profile[1])[1])
            if json_key not in known_json:
                reference_profiles.append(profile)
                known_json.add(json_key)
        data_qualities = {
            key: profile[1]["quality"] for key, profile in zip(data_assets, profiles)
        }
        if any(
            key not in data_qualities
            for bindings in renderer_bindings.values()
            for key in bindings
        ):
            raise ValueError(
                "Prefab renderer points outside this card's verified skeleton profiles."
            )
        quality_bindings = {}
        for quality, bindings in renderer_bindings.items():
            targets = sorted({data_qualities[key] for key in bindings})
            quality_bindings[quality] = targets[0] if len(targets) == 1 else targets
        for quality, renderer, binding, obj, tree in custom_materials:
            profile = next(
                p for p in profiles if p[1]["quality"] == data_qualities[binding]
            )
            self.custom_materials(obj, tree, renderer, profile)
        profiles.extend(reference_profiles)
        events = [
            (p[4].get("events", {}), p[4]["animations"][name].get("events", []))
            for p in profiles
        ]
        if any(event != events[0] for event in events):
            raise ValueError("Profile event timelines differ.")
        return profiles, duration, name, quality_bindings
