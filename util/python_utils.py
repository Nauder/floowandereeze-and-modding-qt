import re
from ast import literal_eval
from os.path import exists, join

from util.constants import FILE


def get_instances_of_subclasses(base_class):
    """
    Returns a list of instances of all subclasses of the given base_class,
    instantiated in alphabetical order of their class names.
    Only creates instances of classes with a parameterless constructor.
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
    try:
        folder = join(folder[:-18], "masterduel_Data", FILE["UNITY"])

        if exists(folder):
            return [True, None]
        else:
            return [False, "Could not locate Unity3D file"]

    except Exception as e:
        return [False, str(e)]


def remove_alt_tags(s):
    return re.sub(r"\(alt \d+\)", "", s).rstrip()


def replace_entry(index: int, list_str: str, new_value: str) -> str:
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
