from abc import ABC, abstractmethod
from os import makedirs
from os.path import join, isfile
from shutil import copyfile
from typing_extensions import Optional

from database.models import UnityAsset
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import slugify

from UnityPy import load as unity_load


class UnityService(ABC):
    """
    UnityService class provides methods for fetching and replacing images from Unity asset bundles.
    """

    def __init__(self, subfolder: str) -> None:
        self.bundle = None
        self.subfolder: str = subfolder
        self.image_path: str | None = None

    @abstractmethod
    def replace_bundle(self) -> None:
        pass

    def extract_texture(self, name: str, field=False, miss=False) -> None:
        self.extract_asset_texture(name, "images", field, miss)

    def create_backup(self, name: str, field=False, miss=False) -> None:
        self.extract_asset_texture(name, "backups", field, miss)

    def extract_asset_texture(
        self, name: str, folder: str, field=False, miss=False
    ) -> None:
        """
        Extracts a texture from a Unity bundle.

        :param field: If the bundle is a field or not.
        :param name: The name of the texture to extract.
        :param miss: A boolean value indicating if the extraction failed to find the bundle.
        :return: None
        """
        found = False

        for obj in unity_load(prepare_environment(miss, self.bundle)).objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                if field:
                    if "01_BaseColor_near" in data.m_Name:
                        found = True
                else:
                    found = True

                if found:
                    makedirs(join(folder, self.subfolder), exist_ok=True)
                    dest = join(folder, self.subfolder, slugify(name) + ".png")

                    img = data.image
                    img.save(dest)
                    break
        else:
            return self.extract_texture(name, field, True)

    def restore_asset(self, backup_name=None) -> bool:
        backup_path = join(
            "backups", self.subfolder, f"{backup_name or self.bundle}.png"
        )
        if isfile(backup_path):
            current_image = self.image_path
            self.image_path = backup_path
            self.replace_bundle()
            self.image_path = current_image
            return True
        return False

    def copy_bundle(self) -> None:
        self.create_bundle_copy("bundles")

    def create_bundle_copy(self, folder="bundles") -> None:
        makedirs(join(folder, self.subfolder), exist_ok=True)

        copyfile(
            join(APP_CONFIG.game_path, "0000", self.bundle[:2], self.bundle),
            join(folder, self.subfolder, self.bundle),
        )
