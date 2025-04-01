from os.path import join, isfile

from UnityPy.enums import TextureFormat
from typing_extensions import override

from database.models import IconModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.enums import IconSize
from util.image_utils import resize_image

from UnityPy import load as unity_load


class IconService(UnityService):

    def __init__(self):
        super().__init__("icons")

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        for bundle, size in zip(
            [
                self.bundle.bundle_small,
                self.bundle.bundle_medium,
                self.bundle.bundle_big,
            ],
            [size.value for size in IconSize],
        ):

            f_path = prepare_environment(False, bundle)
            env = unity_load(f_path)

            for obj in env.objects:
                if obj.type.name == "Texture2D":

                    data = obj.read()

                    img = resize_image(self.image_path, (size, size))

                    data.m_Width, data.m_Height = img.size

                    data.set_image(
                        img=img,
                        target_format=TextureFormat.RGBA32,
                        mipmap_count=APP_CONFIG.mipmap_count,
                    )

                    data.save()
                    break

            with open(f_path, "wb") as f:
                f.write(env.file.save(packer=APP_CONFIG.packer))

    @override
    def copy_bundle(self) -> None:
        current = self.bundle
        for bundle in [
            self.bundle.bundle_big,
            self.bundle.bundle_medium,
            self.bundle.bundle_small,
        ]:
            self.bundle = bundle
            self.create_bundle_copy()
        self.bundle = current

    @override
    def restore_asset(self, backup_name=None) -> bool:
        # If Konami ever puts two icons in the same bundle this whole thing breaks
        self.bundle = (
            session.query(IconModel).filter(IconModel.bundle_big == self.bundle).first()
        )
        backup_path = join("backups", self.subfolder, self.bundle.bundle_big + ".png")
        if isfile(backup_path):
            current_image = self.image_path
            self.image_path = backup_path
            self.replace_bundle()
            self.image_path = current_image
            return True
        return False
