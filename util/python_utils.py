"""
Python utility functions for the application.
This module provides various helper functions for common Python operations
like string manipulation, list handling, and game path validation.
"""

import os
import re
from ast import literal_eval
import logging
from ntpath import normcase, normpath
from os.path import exists, isdir, join

from util.constants import FILE


logger = logging.getLogger(__name__)

try:
    import winreg
except ImportError:
    winreg = None


MASTER_DUEL_DIRECTORY = "Yu-Gi-Oh!  Master Duel"
DEFAULT_MASTER_DUEL_PLAYER_DIRECTORY = "00000000"


def find_steam_master_duel_paths() -> list[str]:
    """Return all valid Master Duel player-data directories found in Steam.

    Steam can be installed outside its usual Windows location and can have games
    distributed across multiple library folders.  The Steam registry keys and
    ``libraryfolders.vdf`` cover both cases.
    """
    game_paths = []
    game_path_keys = set()
    for library_path in _get_steam_library_paths():
        local_data_path = join(
            library_path,
            "steamapps",
            "common",
            MASTER_DUEL_DIRECTORY,
            "LocalData",
        )
        if not isdir(local_data_path):
            continue

        for player_directory in sorted(os.listdir(local_data_path)):
            game_path = join(local_data_path, player_directory)
            if (
                player_directory != DEFAULT_MASTER_DUEL_PLAYER_DIRECTORY
                and isdir(game_path)
                and is_valid_game_path(game_path)[0]
                and _path_key(game_path) not in game_path_keys
            ):
                game_paths.append(game_path)
                game_path_keys.add(_path_key(game_path))

    return game_paths


def _get_steam_library_paths() -> list[str]:
    """Find Steam's main install directory and configured library directories."""
    steam_paths = _get_steam_install_paths()
    library_paths = []
    library_path_keys = set()

    for steam_path in steam_paths:
        if _path_key(steam_path) not in library_path_keys:
            library_paths.append(steam_path)
            library_path_keys.add(_path_key(steam_path))

        library_file = join(steam_path, "steamapps", "libraryfolders.vdf")
        if not exists(library_file):
            continue

        try:
            with open(library_file, encoding="utf-8") as file:
                contents = file.read()
        except OSError:
            continue

        library_matches = re.findall(r'"path"\s+"([^"]+)"', contents)
        library_matches.extend(
            re.findall(r'^\s*"\d+"\s+"([A-Za-z]:[^"]+)"', contents, re.MULTILINE)
        )
        for library_path in library_matches:
            library_path = library_path.replace("\\\\", "\\")
            if _path_key(library_path) not in library_path_keys:
                library_paths.append(library_path)
                library_path_keys.add(_path_key(library_path))

    return library_paths


def _get_steam_install_paths() -> list[str]:
    """Return likely Steam install paths, including the Windows registry value."""
    steam_paths = []

    if winreg:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        steam_path = winreg.QueryValueEx(key, value_name)[0]
                    except FileNotFoundError:
                        continue
                    if steam_path:
                        steam_paths.append(steam_path)
        except OSError:
            pass

    for environment_variable in ("ProgramFiles(x86)", "ProgramFiles"):
        program_files = os.environ.get(environment_variable)
        if program_files:
            steam_paths.append(join(program_files, "Steam"))

    return list(dict.fromkeys(steam_paths))


def _path_key(path: str) -> str:
    """Return a Windows-normalized key for case-insensitive path comparisons."""
    return normcase(normpath(path))


def get_instances_of_subclasses(base_class):
    """
    Returns a list of instances of all subclasses of the given base_class,
    instantiated in alphabetical order of their class names.
    Only creates instances of classes with a parameterless constructor.

    Args:
        base_class: The base class to find subclasses of

    Returns:
        list: List of instances of all subclasses that can be instantiated without arguments
    """
    instances = []
    subclasses = base_class.__subclasses__()  # Get direct subclasses

    # Sort subclasses alphabetically by class name
    sorted_subclasses = sorted(subclasses, key=lambda cls: cls.__name__)

    for subclass in sorted_subclasses:
        # Check if the subclass has a parameterless constructor
        try:
            instance = subclass()  # Try creating an instance
            instances.append(instance)
        except TypeError:
            # Skipping classes that need constructor arguments
            pass

        # Recursively check subclasses of the current subclass
        instances.extend(get_instances_of_subclasses(subclass))

    return instances


def is_valid_game_path(folder: str) -> list[bool | str]:
    """
    Validates if the given folder path contains the required Unity game files.

    Args:
        folder: The folder path to validate

    Returns:
        list[bool | str]: A list containing:
            - bool: True if the path is valid, False otherwise
            - str: Error message if invalid, None if valid
    """
    try:
        folder = join(folder[:-18], "masterduel_Data", FILE["UNITY"])

        if exists(folder):
            return [True, None]
        else:
            return [False, "Could not locate Unity3D file"]

    except Exception as e:
        logger.exception("Game path validation failed for %s", folder)
        return [False, str(e)]


def remove_alt_tags(s):
    """
    Removes alternative tags from a string (e.g., "(alt 1)", "(alt 2)", etc.).

    Args:
        s: The string to clean

    Returns:
        str: The string with alternative tags removed
    """
    return re.sub(r"\(alt \d+\)", "", s).rstrip()


def replace_entry(index: int, list_str: str, new_value: str) -> str:
    """
    Replaces an entry in a string representation of a list at the specified index.

    Args:
        index: The index of the entry to replace
        list_str: String representation of the list
        new_value: The new value to insert at the index

    Returns:
        str: The updated string representation of the list, or an error message if the operation fails
    """
    try:
        # Convert the string representation of the list into an actual list
        parsed_list = literal_eval(list_str)

        # Ensure the parsed object is actually a list
        if not isinstance(parsed_list, list):
            raise ValueError("The provided string does not represent a list.")

        # Replace the value at the given index
        parsed_list[index] = new_value

        # Convert the list back to a string
        return str(parsed_list)

    except (SyntaxError, ValueError, IndexError) as e:
        logger.exception("Could not replace entry %s in serialized list", index)
        return f"Error: {str(e)}"


def max_ratio_within_limit(numbers: tuple[int, int], limit: int) -> tuple[int, int]:
    """
    Scales a pair of numbers while maintaining their ratio, ensuring the larger number
    doesn't exceed the specified limit.

    Args:
        numbers: A tuple of two integers to scale
        limit: The maximum allowed value for the larger number

    Returns:
        tuple[int, int]: The scaled numbers as a tuple, maintaining their original order
    """
    # Unpack the tuple
    num1, num2 = numbers

    # Determine which number is larger
    if num1 > num2:
        larger_num = num1
        smaller_num = num2
    else:
        larger_num = num2
        smaller_num = num1

    # Calculate the scaling factor
    scaling_factor = limit / larger_num

    # Scale both numbers
    scaled_larger = larger_num * scaling_factor
    scaled_smaller = smaller_num * scaling_factor

    # Return the scaled numbers as a tuple, ensuring the order matches the input
    if num1 > num2:
        return int(scaled_smaller), int(scaled_larger)
    else:
        return int(scaled_larger), int(scaled_smaller)
