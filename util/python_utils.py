"""
Python utility functions for the application.
This module provides various helper functions for common Python operations
like string manipulation, list handling, and game path validation.
"""

import re
from ast import literal_eval
from os.path import exists, join

from util.constants import FILE


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
