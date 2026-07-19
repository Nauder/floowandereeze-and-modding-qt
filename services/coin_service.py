from os.path import isfile, join

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat
from typing_extensions import override

from database.models import CoinModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.enums import IconSize
from util.image_utils import resize_image


class CoinService(UnityService):
    """Replace the three size-specific coin bundles with one source image."""

    def __init__(self):
        super().__init__("coins")

    @override
    def replace_bundle(self) -> None:
        """Resize and write the selected image to every coin bundle size."""
        if not self.bundle or not self.image_path:
            return

        for bundle, size in zip(
            (
                self.bundle.bundle_small,
                self.bundle.bundle_medium,
                self.bundle.bundle_big,
            ),
            (size.value for size in IconSize),
        ):
            bundle_path = prepare_environment(False, bundle)
            env = unity_load(bundle_path)

            for obj in env.objects:
                if obj.type.name != "Texture2D":
                    continue

                data = obj.read()
                image = resize_image(self.image_path, (size, size))
                data.m_Width, data.m_Height = image.size
                data.set_image(
                    img=image,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )
                data.save()
                break

            with open(bundle_path, "wb") as bundle_file:
                bundle_file.write(env.file.save(packer=APP_CONFIG.packer))

    @override
    def copy_bundle(self) -> None:
        current_bundle = self.bundle
        for bundle in (
            current_bundle.bundle_big,
            current_bundle.bundle_medium,
            current_bundle.bundle_small,
        ):
            self.bundle = bundle
            self.create_bundle_copy()
        self.bundle = current_bundle

    @override
    def restore_asset(self, backup_name=None) -> bool:
        """Restore all coin sizes from the backup made for the biggest bundle."""
        self.bundle = (
            session.query(CoinModel).filter(CoinModel.bundle_big == self.bundle).first()
        )
        backup_path = join("backups", self.subfolder, f"{self.bundle.bundle_big}.png")
        if not isfile(backup_path):
            return False

        current_image = self.image_path
        self.image_path = backup_path
        self.replace_bundle()
        self.image_path = current_image
        return True
