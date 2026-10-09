"""Deck box orientations with automatic resolution handling."""

from pathlib import Path

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
        with open(bundle_path, "wb") as bundle_file:
            bundle_file.write(env.file.save(packer=APP_CONFIG.packer))

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
