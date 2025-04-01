import io

from unicodedata import normalize
from PIL import Image, ImageChops, ImageOps, ImageDraw
from re import sub

import numpy as np


def add_sleeve_border(image: Image.Image, color: str) -> Image.Image:
    """Adds solid color borders to given image"""

    return ImageOps.expand(
        image, border=(int(image.width * 0.06), int(image.height * 0.05)), fill=color
    )


def trim(im) -> Image.Image:
    """Removes empty space from the image provided"""

    bg = Image.new(im.mode, im.size, im.getpixel((0, 0)))
    diff = ImageChops.difference(im, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)


def slugify(value, allow_unicode=False) -> str:
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """

    value = str(value)
    if allow_unicode:
        value = normalize("NFKC", value)
    else:
        value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = sub(r"[^\w\s-]", "", value.lower())
    return sub(r"[-\s]+", "-", value).strip("-_")


def resize_image(path: str, size: tuple[int, int]) -> Image.Image:
    """Converts the user given image to its proper size using lanczos resampling"""

    return Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)


def convert_image(path: str) -> Image.Image:
    """Converts the user given image to its proper size using lanczos resampling"""

    return Image.open(path).convert("RGBA")


def change_image_ratio(img: Image, new_ratio: tuple):
    width, height = img.size
    original_ratio = width / height
    new_ratio_value = new_ratio[0] / new_ratio[1]

    if original_ratio > new_ratio_value:
        # If the original ratio is greater than target ratio, then reduce width
        new_width = int(height * new_ratio_value)
        left_margin = (width - new_width) / 2
        img = img.crop((left_margin, 0, width - left_margin, height))
    elif original_ratio < new_ratio_value:
        # If the original ratio is less than target ratio, then reduce height
        new_height = int(width / new_ratio_value)
        top_margin = (height - new_height) / 2
        img = img.crop((0, top_margin, width, height - top_margin))

    return img


def add_circle_transparency(image_path) -> Image.Image:
    # Load the image
    img = Image.open(image_path).convert("RGBA")

    # Determine the new size (make it square)
    width, height = img.size
    size = max(width, height)

    # Resize image to square while keeping the aspect ratio
    new_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    new_img.paste(img, ((size - width) // 2, (size - height) // 2))

    # Create a mask for the circle
    mask = Image.new("L", (size, size), 0)  # Create a black mask
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)  # Draw a white circle

    # Apply the mask to the image
    new_img.putalpha(mask)

    return new_img


def overlay_images(
    image1: Image.Image,
    image2: Image.Image,
    coordinates: tuple[int, int],
    size: tuple[int, int],
) -> Image.Image:
    """
    Overlays an image on top of another one, taking the given size starting from the given coordinates.

    :param image1: Image to be overlayed into
    :param image2: Image to be overlayed
    :param coordinates: Coordinates on image1 to overlay (x, y)
    :param size: Size that image2 should take on image1, starting from the top left (width, height)
    :return: Image overlaid
    """

    image1.paste(image2.resize(size), coordinates)

    return image1


def convert_to_png(img: Image.Image) -> Image.Image:
    png_image_buffer = io.BytesIO()
    img.save(png_image_buffer, format="PNG")
    png_image = Image.open(png_image_buffer)
    png_image_buffer.seek(0)

    return png_image


def paste_scaled_image(bg_image, fg_image, bounding_box) -> Image.Image:
    """
    Pastes an image onto a background at specified coordinates, scaling it to fit.

    :param bg_image: PIL Image object for the background
    :param fg_image: PIL Image object for the foreground
    :param bounding_box: Tuple (left, upper, right, lower) defining the bounding box
    """
    # Unpack bounding box
    left, upper, right, lower = bounding_box

    # Resize the foreground image to fit the bounding box
    fg_resized = fg_image.resize(
        (right - left, lower - upper), Image.Resampling.LANCZOS
    )

    # Create a mask for proper blending
    fg_mask = fg_resized.getchannel("A") if fg_resized.mode == "RGBA" else None

    # Paste the resized foreground onto the background
    bg_image.paste(fg_resized, (left, upper), fg_mask)

    return bg_image
