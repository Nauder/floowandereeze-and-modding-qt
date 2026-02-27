from os import makedirs
from os.path import join

from UnityPy.enums import TextureFormat
from typing_extensions import override

from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import convert_image, slugify

from UnityPy import load as unity_load


class FaceService(UnityService):

    def __init__(self):
        super().__init__("faces")
        self.key = None

    @override
    def replace_bundle(self) -> None:
        bundle_path = prepare_environment(False, self.bundle)
        env = unity_load(bundle_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                if obj.path_id == self.key or self.key == data.m_Name:
                    img = convert_image(self.image_path)
                    data.m_Width, data.m_Height = img.size

                    data.set_image(img=img, target_format=TextureFormat.RGBA32)

                    data.save()
                    break

        with open(bundle_path, "wb") as f:
            f.write(env.file.save())

    @override
    def extract_texture(self, name: str, field=False, miss=False, backup=False) -> None:
        bundle_path = prepare_environment(False, self.bundle)

        for obj in unity_load(bundle_path).objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                if obj.path_id == self.key or self.key == data.m_Name:
                    makedirs(
                        join("backups" if backup else "images", self.subfolder),
                        exist_ok=True,
                    )
                    dest = join(
                        "backups" if backup else "images",
                        self.subfolder,
                        slugify(name) + ".png",
                    )

                    img = data.image
                    img.save(dest)

                    break
