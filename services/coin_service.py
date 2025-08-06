import re
from os import makedirs
from os.path import join, isfile
from typing import Optional, Tuple

from PIL import Image, ImageDraw
from UnityPy import load as unity_load

from database.models import CoinModel
from database.objects import session
from services.unity_service import UnityService
from util.constants import APP_CONFIG, COIN
from util.image_utils import slugify


class CoinService(UnityService):
    """
    Service for handling coin asset modifications.

    This service manages the replacement of coin textures by modifying specific
    regions of the coin texture for head and tail areas, leaving the rest untouched.
    """

    def __init__(self):
        super().__init__("coins")
        self.head_image_path: Optional[str] = None
        self.tail_image_path: Optional[str] = None
        self.coin_metadata: Optional[CoinModel] = None
        self.set_coin_metadata()

    def set_coin_metadata(self):
        """Find the first coin metadata from the database."""
        self.coin_metadata = session.query(CoinModel).first()

    def get_coin_regions(
        self, coin_size: Tuple[int, int]
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        """
        Get the head and tail regions of the coin texture.
        Based on the provided coin image, it appears to be a circular coin
        where the bottom half is the head (dragon design) and top half is the tail (dark area).

        Coordinates are calculated based on ratios from the reference size to scale
        properly with different texture sizes.

        Args:
            coin_size: (width, height) of the coin texture

        Returns:
            Tuple of (head_region, tail_region) where each region is (x, y, width, height)
        """
        width, height = coin_size
        ref_width, ref_height = COIN["REFERENCE_SIZE"]

        # Calculate scaling ratios
        width_ratio = width / ref_width
        height_ratio = height / ref_height

        # Scale head region coordinates
        head_start_x = int(COIN["HEAD"]["START"][0] * width_ratio)
        head_start_y = int(COIN["HEAD"]["START"][1] * height_ratio)
        head_end_x = int(COIN["HEAD"]["END"][0] * width_ratio)
        head_end_y = int(COIN["HEAD"]["END"][1] * height_ratio)

        head_region = (
            head_start_x,
            head_start_y,
            head_end_x - head_start_x,
            head_end_y - head_start_y,
        )

        # Scale tail region coordinates
        tail_start_x = int(COIN["TAIL"]["START"][0] * width_ratio)
        tail_start_y = int(COIN["TAIL"]["START"][1] * height_ratio)
        tail_end_x = int(COIN["TAIL"]["END"][0] * width_ratio)
        tail_end_y = int(COIN["TAIL"]["END"][1] * height_ratio)

        tail_region = (
            tail_start_x,
            tail_start_y,
            tail_end_x - tail_start_x,
            tail_end_y - tail_start_y,
        )

        return head_region, tail_region

    def _create_circular_mask(self, size: Tuple[int, int]) -> Image.Image:
        """Create a circular mask for the given size."""
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size[0], size[1]), fill=255)
        return mask

    def _cut_image_to_circle(self, image: Image.Image) -> Image.Image:
        """Cut an image into a circle shape with transparent background."""
        # Create a circular mask
        mask = self._create_circular_mask(image.size)

        # Create a new image with transparent background
        circular_img = Image.new("RGBA", image.size, (0, 0, 0, 0))
        circular_img.paste(image, (0, 0))
        circular_img.putalpha(mask)

        return circular_img

    def replace_bundle(self) -> None:
        """Replace specific regions of the coin texture in the Unity bundle."""
        if not self.coin_metadata:
            raise ValueError("Coin metadata not found in database")

        bundle_path = join(
            APP_CONFIG.game_path,
            "0000",
            self.coin_metadata.bundle[:2],
            self.coin_metadata.bundle,
        )

        env = unity_load(bundle_path)
        modified = False

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                # Look for the coin texture by asset name or common coin texture names
                if re.search(re.compile(r"coin\d\dtex"), data.m_Name.lower()) or (
                    "cointoss" in data.m_Name.lower()
                    and "icon" not in data.m_Name.lower()
                ):

                    # Get the current coin texture
                    current_coin = data.image.convert("RGBA")
                    coin_size = current_coin.size

                    # Get head and tail regions
                    head_region, tail_region = self.get_coin_regions(coin_size)

                    # Replace head region if head image is provided
                    if self.head_image_path:
                        head_img = Image.open(self.head_image_path).convert("RGBA")
                        # Resize head image to fit the head region
                        head_img = head_img.resize(
                            (head_region[2], head_region[3]), Image.Resampling.LANCZOS
                        )
                        # Cut the head image into a circle
                        head_img = self._cut_image_to_circle(head_img)
                        # Paste head image onto the head region
                        current_coin.paste(
                            head_img, (head_region[0], head_region[1]), head_img
                        )
                        modified = True

                    # Replace tail region if tail image is provided
                    if self.tail_image_path:
                        tail_img = Image.open(self.tail_image_path).convert("RGBA")
                        # Resize tail image to fit the tail region
                        tail_img = tail_img.resize(
                            (tail_region[2], tail_region[3]), Image.Resampling.LANCZOS
                        )
                        # Cut the tail image into a circle
                        tail_img = self._cut_image_to_circle(tail_img)
                        # Paste tail image onto the tail region
                        current_coin.paste(
                            tail_img, (tail_region[0], tail_region[1]), tail_img
                        )
                        modified = True

                    if modified:
                        # Update the texture data
                        data.image = current_coin
                        data.save()
                        break

        if modified:
            # Save the modified bundle
            with open(bundle_path, "wb") as f:
                f.write(env.file.save())
        else:
            raise ValueError(
                f"Coin texture not found in bundle (looking for: {self.coin_metadata.bundle})"
            )

    def extract_texture(self, name: str, field=False, miss=False) -> None:
        """Extract the full coin texture and separate head/tail regions."""
        if not self.coin_metadata:
            return

        bundle_path = join(
            APP_CONFIG.game_path,
            "0000",
            self.coin_metadata.bundle[:2],
            self.coin_metadata.bundle,
        )

        try:
            env = unity_load(bundle_path)
        except:
            if not miss:
                return self.extract_texture(name, field, True)
            return

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                # Look for the coin texture
                if re.search(re.compile(r"coin\d\dtex"), data.m_Name.lower()) or (
                    "cointoss" in data.m_Name.lower()
                    and "icon" not in data.m_Name.lower()
                ):

                    # Extract the full coin texture
                    coin_img = data.image.convert("RGBA")

                    # Save full coin texture
                    makedirs(join("images", self.subfolder), exist_ok=True)
                    full_coin_path = join(
                        "images", self.subfolder, f"{slugify(name)}_full.png"
                    )
                    coin_img.save(full_coin_path)

                    # Get head and tail regions
                    head_region, tail_region = self.get_coin_regions(coin_img.size)

                    # Extract and save head region
                    head_img = coin_img.crop(
                        (
                            head_region[0],
                            head_region[1],
                            head_region[0] + head_region[2],
                            head_region[1] + head_region[3],
                        )
                    )
                    head_path = join(
                        "images", self.subfolder, f"{slugify(name)}_head.png"
                    )
                    head_img.save(head_path)

                    # Extract and save tail region
                    tail_img = coin_img.crop(
                        (
                            tail_region[0],
                            tail_region[1],
                            tail_region[0] + tail_region[2],
                            tail_region[1] + tail_region[3],
                        )
                    )
                    tail_path = join(
                        "images", self.subfolder, f"{slugify(name)}_tail.png"
                    )
                    tail_img.save(tail_path)

                    break

    def create_backup(self, name: str, field=False, miss=False) -> None:
        """Create a backup of the current coin texture."""
        if not self.coin_metadata:
            return

        bundle_path = join(
            APP_CONFIG.game_path,
            "0000",
            self.coin_metadata.bundle[:2],
            self.coin_metadata.bundle,
        )

        try:
            env = unity_load(bundle_path)
        except:
            if not miss:
                return self.create_backup(name, field, True)
            return

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                # Look for the coin texture
                if re.search(re.compile(r"coin\d\dtex"), data.m_Name.lower()) or (
                    "cointoss" in data.m_Name.lower()
                    and "icon" not in data.m_Name.lower()
                ):

                    # Save the full coin texture as backup
                    makedirs(join("backups", self.subfolder), exist_ok=True)
                    backup_path = join(
                        "backups", self.subfolder, f"{slugify(name)}_full.png"
                    )

                    coin_img = data.image.convert("RGBA")
                    coin_img.save(backup_path)
                    break

    def restore_asset(self, backup_name=None) -> bool:
        """Restore coin from full texture backup."""
        backup_path = join(
            "backups", self.subfolder, f"{backup_name or 'coin'}_full.png"
        )

        if isfile(backup_path):

            try:
                bundle_path = join(
                    APP_CONFIG.game_path,
                    "0000",
                    self.coin_metadata.bundle[:2],
                    self.coin_metadata.bundle,
                )

                env = unity_load(bundle_path)

                for obj in env.objects:
                    if obj.type.name == "Texture2D":
                        data = obj.read()

                        # Look for the coin texture
                        if re.search(
                            re.compile(r"coin\d\dtex"), data.m_Name.lower()
                        ) or (
                            "cointoss" in data.m_Name.lower()
                            and "icon" not in data.m_Name.lower()
                        ):

                            # Restore from backup
                            backup_img = Image.open(backup_path).convert("RGBA")
                            data.image = backup_img
                            data.save()

                            # Save the modified bundle
                            with open(bundle_path, "wb") as f:
                                f.write(env.file.save())

                            return True

            except Exception as e:
                print(f"Error restoring coin from backup: {str(e)}")
                return False

        return False
