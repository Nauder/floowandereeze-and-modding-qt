from UnityPy.enums import TextureFormat
from typing_extensions import override

from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from UnityPy import load as unity_load

from util.constants import APP_CONFIG
from util.image_utils import add_sleeve_border, convert_image


class SleeveService(UnityService):

    def __init__(self):
        super().__init__("sleeves")
        self.border: bool | None = None
        self.border_color: str | None = "#FFFFFF"

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        f_path = prepare_environment(False, self.bundle)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":

                data = obj.read()

                img = (
                    add_sleeve_border(convert_image(self.image_path), self.border_color)
                    if self.border
                    else convert_image(self.image_path)
                )

                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=img,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )

                data.save()
                break

            type_tree = obj.read_typetree()
            if (
                obj.type.name == "Material"
                and "_LightPower" in type_tree["m_SavedProperties"]["m_Floats"][10][0]
            ):
                type_tree["m_SavedProperties"]["m_Floats"][10] = (
                    "_LightPower",
                    0.0,
                )
                obj.save_typetree(type_tree)

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))
