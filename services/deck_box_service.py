"""Deck box orientations with automatic resolution handling."""

from pathlib import Path
from struct import pack

from PIL import Image
from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import convert_image

DECK_BOX_VARIANTS = (
    ("Normal", ("small", "medium", "large")),
    ("Left Facing", ("r_medium", "r_large")),
    ("Open", ("o_medium", "o_large")),
)


class DeckBoxService(UnityService):
    """Keep all resolutions of an orientation together."""

    def __init__(self):
        super().__init__("deck_boxes")
        self.bundles = ()

    def select_variant(self, asset, fields):
        """Use the largest bundle for display and every size for edits."""
        self.bundles = tuple(getattr(asset, field) for field in fields)
        self.bundle = self.bundles[-1]

    def _target_bundles(self):
        # Bulk maintenance assigns bundle directly from backup filenames.
        if self.bundles and self.bundle == self.bundles[-1]:
            return self.bundles
        return (self.bundle,)

    def texture_size(self):
        """Read the selected texture's native dimensions."""
        for obj in unity_load(prepare_environment(False, self.bundle)).objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                return data.m_Width, data.m_Height
        raise ValueError("No texture found in the selected deck box bundle")

    def ensure_backup(self):
        """Preserve each resolution's original texture independently."""
        current_bundle = self.bundle
        try:
            for bundle in self._target_bundles():
                self.bundle = bundle
                if not Path("backups", self.subfolder, f"{bundle}.png").is_file():
                    self.create_backup(bundle)
        finally:
            self.bundle = current_bundle

    def replace_bundle(self):
        """Write the same artwork at every resolution of this orientation."""
        if not self.bundle or not self.image_path:
            return
        for bundle in self._target_bundles():
            self._replace_texture(bundle, self.image_path)

    def _replace_texture(self, bundle, image_path):
        bundle_path = prepare_environment(False, bundle)
        env = unity_load(bundle_path)
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            data = obj.read()
            image = convert_image(image_path).resize(
                (data.m_Width, data.m_Height), Image.Resampling.LANCZOS
            )
            data.set_image(
                img=image,
                target_format=TextureFormat.RGBA32,
                mipmap_count=APP_CONFIG.mipmap_count,
            )
            data.save()
            break
        else:
            raise ValueError("No texture found in the selected deck box bundle")
        self._expand_sprites(env, obj.path_id, image.size)
        with open(bundle_path, "wb") as bundle_file:
            bundle_file.write(env.file.save(packer=APP_CONFIG.packer))

    @staticmethod
    def _expand_sprites(env, texture_id, texture_size):
        """Remove the original artwork's tight mesh from matching sprites."""
        texture_width, texture_height = texture_size
        for obj in env.objects:
            if obj.type.name != "Sprite":
                continue
            sprite = obj.read_typetree()
            render = sprite["m_RD"]
            texture = render["texture"]
            if texture["m_FileID"] != 0 or texture["m_PathID"] != texture_id:
                continue

            rect = sprite["m_Rect"]
            width, height = rect["width"], rect["height"]
            pivot = sprite["m_Pivot"]
            units = sprite["m_PixelsToUnits"]
            left, bottom = -pivot["x"] * width / units, -pivot["y"] * height / units
            right, top = left + width / units, bottom + height / units
            positions = (
                (left, bottom, 0),
                (left, top, 0),
                (right, top, 0),
                (right, bottom, 0),
            )
            u0, v0 = rect["x"] / texture_width, rect["y"] / texture_height
            u1 = (rect["x"] + width) / texture_width
            v1 = (rect["y"] + height) / texture_height
            uvs = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))

            # Unity stores positions and UVs in separate, 16-byte-aligned streams.
            vertex_data = render["m_VertexData"]
            for channel in vertex_data["m_Channels"]:
                channel.update(stream=0, offset=0, format=0, dimension=0)
            vertex_data["m_Channels"][0].update(dimension=3)
            vertex_data["m_Channels"][4].update(stream=1, dimension=2)
            vertex_data["m_VertexCount"] = 4
            vertex_data["m_DataSize"] = b"".join(
                pack("<3f", *point) for point in positions
            ) + b"".join(pack("<2f", *uv) for uv in uvs)
            render["m_IndexBuffer"] = list(pack("<6H", 0, 1, 2, 0, 2, 3))
            submesh = render["m_SubMeshes"][0]
            submesh.update(
                firstByte=0,
                indexCount=6,
                topology=0,
                baseVertex=0,
                firstVertex=0,
                vertexCount=4,
            )
            submesh["localAABB"] = {
                "m_Center": {"x": (left + right) / 2, "y": (bottom + top) / 2, "z": 0},
                "m_Extent": {"x": width / units / 2, "y": height / units / 2, "z": 0},
            }
            render["m_SubMeshes"] = [submesh]
            render["textureRect"] = dict(rect)
            render["textureRectOffset"] = {"x": 0.0, "y": 0.0}
            render["atlasRectOffset"] = {"x": 0.0, "y": 0.0}
            render["settingsRaw"] &= ~(1 << 6)  # SpriteMeshType.FullRect
            obj.save_typetree(sprite)

    def restore_asset(self, backup_name=None):
        """Restore a single backup, including during bulk maintenance."""
        backup = Path("backups", self.subfolder, f"{backup_name or self.bundle}.png")
        if not backup.is_file():
            return False
        self._replace_texture(self.bundle, str(backup))
        return True

    def restore_variant(self):
        """Restore every resolution only when all original backups exist."""
        bundles = self._target_bundles()
        if not all(
            Path("backups", self.subfolder, f"{bundle}.png").is_file()
            for bundle in bundles
        ):
            return False
        for bundle in bundles:
            backup = Path("backups", self.subfolder, f"{bundle}.png")
            self._replace_texture(bundle, str(backup))
        return True

    def copy_bundle(self):
        """Copy every resolution of the selected orientation."""
        current_bundle = self.bundle
        try:
            for bundle in self._target_bundles():
                self.bundle = bundle
                self.create_bundle_copy()
        finally:
            self.bundle = current_bundle
