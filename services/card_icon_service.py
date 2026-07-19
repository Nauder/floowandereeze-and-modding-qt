"""Card Icon Service Module.

This module provides service functionality for handling card icon asset modifications.
It manages the replacement of card icons within the sprite atlas.
"""

from os import makedirs
from os.path import join, isfile
from typing import Optional

from PIL import Image
from UnityPy import load as unity_load

from database.models import CardIconModel
from services.unity_service import UnityService
from util.constants import APP_CONFIG, FILE
from util.image_utils import slugify


class CardIconService(UnityService):
    """
    Service for handling card icon asset modifications.

    This service manages the replacement of card icons by modifying specific
    regions of the card sprite atlas texture.
    """

    def __init__(self):
        super().__init__("icons")
        self.selected_icon: Optional[CardIconModel] = None

    def _atlas_path(self) -> str:
        """Return the Unity data file that contains the card icon atlas."""
        return join(APP_CONFIG.game_path[:-18], "masterduel_Data", FILE["UNITY"])

    def replace_bundle(self) -> None:
        """Replace the card icon in the sprite atlas with a new image."""
        if not self.selected_icon or not self.image_path:
            raise ValueError("No icon selected or image path not set")

        # Load the card sprite atlas
        atlas_path = self._atlas_path()

        env = unity_load(atlas_path)
        modified = False

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                # Look for the card sprite atlas texture
                if FILE["CARD_SPRITE_ATLAS"] in data.m_Name.lower():
                    # Get the current atlas texture
                    current_atlas = data.image.convert("RGBA")

                    # Load and resize the new icon image
                    new_icon = Image.open(self.image_path).convert("RGBA")
                    new_icon = new_icon.resize(
                        (self.selected_icon.width, self.selected_icon.height),
                        Image.Resampling.LANCZOS,
                    )

                    # Replace the whole region, including transparent pixels.
                    current_atlas.paste(
                        new_icon, (self.selected_icon.x, self.selected_icon.y)
                    )

                    # Update the texture data
                    data.image = current_atlas
                    data.save()
                    modified = True
                    break

        if modified:
            # Save the modified bundle
            with open(atlas_path, "wb") as f:
                f.write(env.file.save())
        else:
            raise ValueError("Card sprite atlas texture not found in bundle")

    def extract_texture(self, name: str, field=False, miss=False) -> str:
        """Extract the card icon texture."""
        if not self.selected_icon:
            raise ValueError("No icon selected")

        atlas_path = self._atlas_path()
        env = unity_load(atlas_path)

        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue

            data = obj.read()

            # Look for the card sprite atlas texture
            if FILE["CARD_SPRITE_ATLAS"] not in data.m_Name.lower():
                continue

            atlas_img = data.image.convert("RGBA")

            # Extract the icon region
            icon_img = atlas_img.crop(
                (
                    self.selected_icon.x,
                    self.selected_icon.y,
                    self.selected_icon.x + self.selected_icon.width,
                    self.selected_icon.y + self.selected_icon.height,
                )
            )

            # Save the extracted icon
            makedirs(join("images", self.subfolder), exist_ok=True)
            icon_path = join("images", self.subfolder, f"{slugify(name)}.png")
            icon_img.save(icon_path)
            return icon_path

        raise ValueError("Card sprite atlas texture not found in bundle")

    def create_backup(self, name: str, field=False, miss=False) -> None:
        """Create a backup of the current card icon."""
        if not self.selected_icon:
            return

        try:
            # Load the card sprite atlas
            atlas_path = self._atlas_path()
            env = unity_load(atlas_path)

            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    data = obj.read()

                    # Look for the card sprite atlas texture
                    if FILE["CARD_SPRITE_ATLAS"] in data.m_Name.lower():
                        atlas_img = data.image.convert("RGBA")

                        # Extract the icon region
                        icon_img = atlas_img.crop(
                            (
                                self.selected_icon.x,
                                self.selected_icon.y,
                                self.selected_icon.x + self.selected_icon.width,
                                self.selected_icon.y + self.selected_icon.height,
                            )
                        )

                        # Save the backup
                        makedirs(join("backups", self.subfolder), exist_ok=True)
                        backup_path = join(
                            "backups", self.subfolder, f"{slugify(name)}.png"
                        )
                        icon_img.save(backup_path)
                        break

        except Exception as e:
            print(f"Error creating card icon backup: {e}")

    def restore_asset(self, backup_name=None) -> bool:
        """Restore card icon from backup."""
        if not self.selected_icon:
            return False

        backup_path = join(
            "backups",
            self.subfolder,
            f"{backup_name or slugify(self.selected_icon.name)}.png",
        )

        if isfile(backup_path):
            try:
                # Temporarily set the backup as the image path
                original_path = self.image_path
                self.image_path = backup_path

                # Replace with the backup
                self.replace_bundle()

                # Restore original path
                self.image_path = original_path

                return True

            except Exception as e:
                print(f"Error restoring card icon from backup: {str(e)}")
                self.image_path = original_path
                return False

        return False
