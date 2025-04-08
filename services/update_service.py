"""
This module provides functionality to update the database with the latest data from the remote
source.
"""

import requests
from requests.exceptions import RequestException, Timeout, HTTPError
from pandas import read_parquet, DataFrame
from pandas.errors import EmptyDataError

from database.models import (
    SleeveModel,
    CardModel,
    FaceModel,
    WallpaperModel,
    FieldModel,
    IconModel,
    DeckBoxModel,
    CardMetadataModel,
)
from database.objects import session


def get_github_raw_file(
    path: str, owner="Nauder", repo="floowandereeze-and-modding-etl"
) -> str:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.

    :return: The raw content of the file.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    """
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        # Send a GET request to fetch file metadata
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses

        file_data = response.json()

        # Extract the download URL from the response
        if "download_url" not in file_data:
            raise ValueError("No download URL found in the response.")

        raw_url = file_data["download_url"]

        # Send a second GET request to fetch the raw file content
        raw_response = requests.get(raw_url, headers=headers, timeout=10)
        raw_response.raise_for_status()

        return raw_response.text

    except Timeout as e:
        raise Timeout(f"Request timed out: {str(e)}") from e
    except HTTPError as e:
        raise HTTPError(f"GitHub API request failed: {str(e)}") from e
    except RequestException as e:
        raise RequestException(f"Request failed: {str(e)}") from e


def get_github_parquet_file(
    path: str, owner="Nauder", repo="floowandereeze-and-modding-etl"
) -> DataFrame:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.

    :return: The raw content of the file as a pandas DataFrame.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    :raises EmptyDataError: If the parquet file is empty or invalid
    """
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        # Send a GET request to fetch file metadata
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        file_data = response.json()

        # Extract the download URL from the response
        if "download_url" not in file_data:
            raise ValueError("No download URL found in the response.")

        raw_url = file_data["download_url"]

        return read_parquet(raw_url)

    except Timeout as e:
        raise Timeout(f"Request timed out: {str(e)}") from e
    except HTTPError as e:
        raise HTTPError(f"GitHub API request failed: {str(e)}") from e
    except RequestException as e:
        raise RequestException(f"Request failed: {str(e)}") from e
    except EmptyDataError as e:
        raise EmptyDataError(f"Failed to read parquet file: {str(e)}") from e


def update_sleeves():
    """
    Updates the sleeves in the database by completely replacing all existing sleeves
    with the latest data from the remote source.

    This function:
    1. Fetches the latest sleeves data from the remote parquet file
    2. Deletes all existing sleeves from the database
    3. Adds all sleeves from the remote data
    """
    remote_sleeves = get_github_parquet_file("data/sleeves.parquet")
    session.query(SleeveModel).delete()
    session.add_all([SleeveModel(bundle=sleeve) for sleeve in remote_sleeves["bundle"]])


def update_cards():
    """
    Updates the cards in the database by completely replacing all existing cards
    with the latest data from the remote source.

    This function:
    1. Fetches the latest cards data from the remote parquet file
    2. Deletes all existing cards from the database
    3. Adds all cards from the remote data with their bundle, name, description, and data_index
    """
    remote_cards = get_github_parquet_file("data/cards.parquet")
    session.query(CardModel).delete()
    session.add_all(
        [
            CardModel(
                bundle=card["bundle"],
                name=card["name"],
                description=card["description"],
                data_index=card["data_index"],
            )
            for _, card in remote_cards.iterrows()
        ]
    )


def update_faces():
    """
    Updates the faces in the database by completely replacing all existing faces
    with the latest data from the remote source.

    This function:
    1. Fetches the latest faces data from the remote parquet file
    2. Deletes all existing faces from the database
    3. Adds all faces from the remote data with their key and name
    """
    remote_faces = get_github_parquet_file("data/faces.parquet")
    session.query(FaceModel).delete()
    session.add_all(
        [
            FaceModel(key=face["key"], name=face["name"])
            for _, face in remote_faces.iterrows()
        ]
    )


def update_wallpapers():
    """
    Updates the wallpapers in the database by completely replacing all existing wallpapers
    with the latest data from the remote source.

    This function:
    1. Fetches the latest wallpapers data from the remote parquet file
    2. Deletes all existing wallpapers from the database
    3. Adds all wallpapers from the remote data with their name, icon, background,
    and foreground bundles
    """
    remote_wallpapers = get_github_parquet_file("data/wallpapers.parquet")
    session.query(WallpaperModel).delete()
    session.add_all(
        [
            WallpaperModel(
                name=wallpaper["name"],
                bundle_icon=wallpaper["icon"],
                bundle_background=wallpaper["back"],
                bundle_foreground=wallpaper["front"],
            )
            for _, wallpaper in remote_wallpapers.iterrows()
        ]
    )


def update_fields():
    """
    Updates the fields in the database by completely replacing all existing fields
    with the latest data from the remote source.

    This function:
    1. Fetches the latest fields data from the remote parquet file
    2. Deletes all existing fields from the database
    3. Adds all fields from the remote data with their bundle, flipped, and bottom properties
    """
    remote_fields = get_github_parquet_file("data/fields.parquet")
    session.query(FieldModel).delete()
    session.add_all(
        [
            FieldModel(
                bundle=field["bundle"], flipped=field["flipped"], bottom=field["bottom"]
            )
            for _, field in remote_fields.iterrows()
        ]
    )


def update_icons():
    """
    Updates the icons in the database by completely replacing all existing icons
    with the latest data from the remote source.

    This function:
    1. Fetches the latest icons data from the remote parquet file
    2. Deletes all existing icons from the database
    3. Adds all icons from the remote data with their name and bundle sizes (small, medium, large)
    """
    remote_icons = get_github_parquet_file("data/icons.parquet")
    session.query(IconModel).delete()
    session.add_all(
        [
            IconModel(
                name=icon["name"],
                bundle_small=icon["small"],
                bundle_medium=icon["medium"],
                bundle_big=icon["large"],
            )
            for _, icon in remote_icons.iterrows()
        ]
    )


def update_boxes():
    """
    Updates the deck boxes in the database by completely replacing all existing boxes
    with the latest data from the remote source.

    This function:
    1. Fetches the latest deck boxes data from the remote parquet file
    2. Deletes all existing deck boxes from the database
    3. Adds all deck boxes from the remote data with their name and various size bundles
    """
    remote_boxes = get_github_parquet_file("data/deck_boxes.parquet")
    session.query(DeckBoxModel).delete()
    session.add_all(
        [
            DeckBoxModel(
                name=box["name"],
                small=box["small"],
                medium=box["medium"],
                o_medium=box["o_medium"],
                r_medium=box["r_medium"],
                large=box["large"],
                o_large=box["o_large"],
                r_large=box["r_large"],
            )
            for _, box in remote_boxes.iterrows()
        ]
    )


def update_card_metadata():
    """
    Updates the card metadata in the database by completely replacing all existing metadata
    with the latest data from the remote source.

    This function:
    1. Fetches the latest card metadata from the remote parquet file
    2. Deletes all existing card metadata from the database
    3. Adds all card metadata from the remote data with their name and bundle
    """
    remote_data = get_github_parquet_file("data/metadata.parquet")
    session.query(CardMetadataModel).delete()
    session.add_all(
        [
            CardMetadataModel(name=data["name"], bundle=data["bundle"])
            for _, data in remote_data.iterrows()
        ]
    )
