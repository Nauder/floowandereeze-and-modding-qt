from os.path import join, isfile

from PIL import Image
from UnityPy.enums import TextureFormat
from typing_extensions import override

from database.models import IconModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG

from UnityPy import load as unity_load


class WallpaperService(UnityService):

    def __init__(self):
        super().__init__("wallpapers")

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        self.remove_image(self.bundle.bundle_background)

        f_path = prepare_environment(False, self.bundle.bundle_foreground)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":

                data = obj.read()

                img = Image.open(self.image_path)

                wallpaper = data.image
                img.thumbnail(
                    (wallpaper.width, wallpaper.height),
                    Image.Resampling.LANCZOS,
                )
                new_img = Image.new("RGBA", wallpaper.size)
                new_img.paste(img)

                img = new_img

                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=img, target_format=TextureFormat.RGBA32, mipmap_count=10
                )

                data.save()
                break

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))

    def remove_image(self, bundle):
        f_path = prepare_environment(False, bundle)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                new_img = Image.new("RGBA", (data.m_Width, data.m_Height))

                data.set_image(
                    img=new_img, target_format=TextureFormat.RGBA32, mipmap_count=1
                )

                data.save()
                break

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))

    @override
    def copy_bundle(self) -> None:
        current = self.bundle
        for bundle in [self.bundle.bundle_foreground, self.bundle.bundle_background]:
            self.bundle = bundle
            self.create_bundle_copy()
        self.bundle = current

    @override
    def restore_asset(self) -> bool:
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
