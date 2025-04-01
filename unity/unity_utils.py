from os import remove
from os.path import join
from shutil import copyfile

from PIL.ImageQt import ImageQt
from PySide6 import QtGui
from UnityPy import load as unity_load

from PIL import Image
from UnityPy.enums import TextureFormat
from sqlalchemy.orm import Mapped

from database.models import FieldModel
from util.constants import FILE, APP_CONFIG
from util.enums import FieldCoordinates
from util.image_utils import slugify, convert_to_png


def prepare_environment(miss: bool, bundle: str) -> str:
    """returns the UnityPy environment path related to the bundle and game path given"""

    return (
        join(
            APP_CONFIG.game_path[:-18],
            "masterduel_Data",
            "StreamingAssets",
            "AssetBundle",
            bundle[:2],
            bundle,
        )
        if miss
        else join(APP_CONFIG.game_path, "0000", bundle[:2], bundle)
    )


def fetch_unity3d_image(path_id: int, aspect: tuple) -> QtGui.QIcon | None:
    """
    Fetch and resize an image from Unity3D resources.

    This function fetches an image with a specified Unity3D path ID, resizes it to the given aspect ratio, and
    converts it into RGB format.

    :param path_id: The path ID of the image in Unity3D resources.
    :type path_id: str
    :param aspect: A tuple representing the desired width and height for the image to be resized to.
    :type aspect: tuple
    :return: The resized and converted RGB image from Unity3D resources.
    :rtype: Image.Image
    """
    env = unity_load(join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"]))

    for obj in env.objects:
        if obj.type.name == "Texture2D" and obj.path_id == path_id:
            data = obj.read()
            img = data.image.resize(aspect)
            img.convert("RGB")
            img.name = "image.jpg"

            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

            return icon


def batch_fetch_unity3d_images(path_ids: list[int], aspect: tuple) -> dict[QtGui.QIcon]:
    """
    Fetch and resize an image from Unity3D resources.

    This function fetches images with specified Unity3D path IDs in bulk, resizes them to the given aspect ratio,
    and converts them into RGB format.

    :param path_ids: The path IDs of the images in Unity3D resources.
    :type path_ids: list[int]
    :param aspect: A tuple representing the desired width and height for the image to be resized to.
    :type aspect: tuple
    :return: The resized and converted RGB images from Unity3D resources.
    :rtype: QtGui.QIcon
    """
    env = unity_load(join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"]))

    images: dict[QtGui.QIcon] = {}

    for obj in env.objects:
        if obj.type.name == "Texture2D" and obj.path_id in path_ids:
            data = obj.read()
            img = data.image.resize(aspect)
            img.name = "image.jpg"

            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

            images[obj.path_id] = icon

    return images


def replace_unity3d_asset(asset: str, img: Image.Image, by_path_id=False) -> None:
    env = unity_load(join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"]))

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()
            if by_path_id and str(obj.path_id) == asset or asset == data.m_Name:
                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=convert_to_png(img),
                    target_format=TextureFormat.RGBA32,
                )

                data.save()
                break

    with open(
        join(APP_CONFIG.game_path[:-18], "masterduel_Data", "data.unity3d"), "wb"
    ) as f:
        f.write(env.file.save())


def extract_unity3d_image(asset: str, by_id=False, backup=False) -> None:
    """
    Extracts an image from Unity3D game data.

    This function locates either by asset ID or by name a texture
    object within Unity3D game data file and then saves it as a PNG file.

    :param asset: If `by_id` is False, it represents the name of the texture.
                  Otherwise, it is the texture's id.

    :param by_id: It is a flag used to switch between searching asset by its name or by its id.
                  By default, it is False, i.e., the function searches by name.

    :param backup: It is a flag used to switch between the images or backups folder.

    :type asset: str

    :type by_id: bool, optional

    :returns: None. The function handles the saving of the image internally, therefore doesn't return anything.

    :raises FileNotFoundError: If the Unity3D game file path doesn't exist or the asset is not found within the game
     file.

    **Notes**

    The image is saved in a directory named "images". Be sure this directory exists
    in the current working directory or else this function will raise an IOError.

    """
    for obj in unity_load(
        join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"])
    ).objects:
        if obj.type.name == "Texture2D":
            data = obj.read()
            if by_id:
                if str(obj.path_id) == asset:
                    dest = join(
                        "backups" if backup else "images", slugify(data.m_Name) + ".png"
                    )
                    img = data.image
                    img.save(dest)
                    break
            else:
                if asset == data.m_Name:
                    dest = join(
                        "backups" if backup else "images", slugify(data.m_Name) + ".png"
                    )
                    img = data.image
                    img.save(dest)
                    break


def fetch_home_bg():
    env = unity_load(join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"]))
    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()
            if FILE["BACKGROUND"] == data.m_Name:
                img = data.image.resize((1120, 630))
                img.convert("RGB")
                img.name = FILE["IMAGE_NAME"]

                icon = QtGui.QIcon()
                icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

                return icon


def swap_bundles(bundles: list) -> None:
    """Swaps the content of two given bundles"""
    asset_1 = join(APP_CONFIG.game_path, "0000", bundles[0][:2], bundles[0])
    asset_2 = join(APP_CONFIG.game_path, "0000", bundles[1][:2], bundles[1])
    copyfile(asset_1, join(APP_CONFIG.game_path, bundles[0]))
    copyfile(asset_2, asset_1)
    copyfile(join(APP_CONFIG.game_path, bundles[0]), asset_2)
    remove(join(APP_CONFIG.game_path, bundles[0]))


def fetch_bundle_thumb(
    bundle: str | Mapped[str], ratio: tuple[int, int] | None, unity_file=False
) -> QtGui.QIcon | None:

    env = unity_load(prepare_environment(unity_file, bundle))

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()

            img = data.image.resize(ratio) if ratio else data.image

            img.name = FILE["IMAGE_NAME"]

            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

            return icon


def fetch_field_thumb(field: FieldModel) -> QtGui.QIcon | None:

    env = unity_load(prepare_environment(False, field.bundle))

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()

            if (
                "01_BaseColor_far" in data.m_Name
                if False
                else "01_BaseColor_near" in data.m_Name
            ):

                img: Image.Image = data.image

                if not field.bottom:
                    if field.flipped:
                        img_field = img.crop(FieldCoordinates.FLIPPED.value).rotate(180)
                    else:
                        img_field = img.crop(FieldCoordinates.TOP.value)
                else:
                    if field.flipped:
                        img_field = img.crop(
                            FieldCoordinates.BOTTOM_FLIPPED.value
                        ).rotate(180)
                    else:
                        img_field = img.crop(FieldCoordinates.BOTTOM.value)

                img_field.thumbnail((900, img_field.size[1]), Image.Resampling.LANCZOS)
                img = img_field

                img.name = FILE["IMAGE_NAME"]

                icon = QtGui.QIcon()
                icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

                return icon
