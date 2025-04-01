from enum import Enum


class FieldCoordinates(Enum):
    """
    Coordinates of crop areas of each type of field, in pixels.
    """

    FLIPPED = (0, 311, 2048, 1023)
    TOP = (0, 243, 2048, 955)
    BOTTOM_FLIPPED = (0, 1024, 2048, 1736)
    BOTTOM = (0, 1024, 2048, 1736)


class IconSize(Enum):
    """
    Sizes of the different resolutions of the player icon, in pixels.
    """

    SMALL = 128
    MEDIUM = 256
    BIG = 512
