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


def add_sleeve_border_with_fade(image: Image.Image, color: str) -> Image.Image:
    """Adds borders with fade-in effect that blends with the image content"""

    # Calculate border sizes
    border_width = int(image.width * 0.05)
    border_height = int(image.height * 0.04)

    # Create new image with border space
    new_width = image.width + 2 * border_width
    new_height = image.height + 2 * border_height

    # Parse color
    original_color = color
    if color.startswith("#"):
        color = color[1:]
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)

    # Convert original image to RGBA if needed
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # First, expand the image with the border color (like the solid border)
    result = ImageOps.expand(
        image, border=(border_width, border_height), fill=original_color
    )

    # Convert to numpy arrays for gradient processing
    result_array = np.array(result).astype(np.float32)
    original_array = np.array(image).astype(np.float32)

    # Create fade effect that only extends inward into the image content
    fade_distance = (
        min(border_width, border_height) * 2.0
    )  # Fade distance for inner transition

    # Process each pixel to create the gradient blend
    for y in range(new_height):
        for x in range(new_width):
            # Get original image coordinates
            orig_x = x - border_width
            orig_y = y - border_height

            # Check if we're in the original image area
            if 0 <= orig_x < image.width and 0 <= orig_y < image.height:
                # We're in the image content area - apply fade based on distance to border

                # Calculate distance to the border (content boundary)
                dist_to_border_left = orig_x
                dist_to_border_right = image.width - 1 - orig_x
                dist_to_border_top = orig_y
                dist_to_border_bottom = image.height - 1 - orig_y

                # Find minimum distance to any border edge
                min_border_dist = min(
                    dist_to_border_left,
                    dist_to_border_right,
                    dist_to_border_top,
                    dist_to_border_bottom,
                )

                # Only apply fade if we're close to the border
                if min_border_dist < fade_distance:
                    # Calculate fade factor based on distance from border
                    base_fade_factor = min_border_dist / fade_distance

                    # Apply double smoothstep for ultra-soft transition
                    smooth1 = (
                        base_fade_factor
                        * base_fade_factor
                        * (3.0 - 2.0 * base_fade_factor)
                    )
                    smooth2 = smooth1 * smooth1 * (3.0 - 2.0 * smooth1)

                    # Exponential softening
                    fade_factor = 1.0 - np.exp(-4.0 * smooth2)

                    # Blend between border color and original image
                    original_pixel = original_array[orig_y, orig_x]
                    border_color = np.array([r, g, b, 255], dtype=np.float32)

                    # Smooth interpolation - fade_factor 0 = border color, 1 = original image
                    blended_pixel = (
                        1 - fade_factor
                    ) * border_color + fade_factor * original_pixel
                    result_array[y, x] = blended_pixel
                else:
                    # Far from border - keep original image
                    result_array[y, x] = original_array[orig_y, orig_x]
            else:
                # Outside original image bounds - solid border color (no fade on outer edges)
                result_array[y, x] = [r, g, b, 255]

    # Convert back to PIL Image
    result = Image.fromarray(result_array.astype(np.uint8), "RGBA")

    return result


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
