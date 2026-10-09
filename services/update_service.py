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
    SleeveOcgModel,
    CardModel,
    CardOcgModel,
    CardIconModel,
    FaceModel,
    WallpaperModel,
    FieldModel,
    IconModel,
    DeckBoxModel,
    CardMetadataModel,
    CoinModel,
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


def _merge_metadata(model, remote_data: DataFrame, key: str, columns: dict) -> None:
    """Refresh remote-owned columns, preserving local state and missing records.

    Keys identify assets independently of their database IDs. Include pending
    inserts because the shared session has autoflush disabled and the caller
    controls when updates are committed.
    """
    records = {getattr(record, key): record for record in session.query(model).all()}
    records.update(
        (getattr(record, key), record)
        for record in session.new
        if isinstance(record, model)
    )
    for _, row in remote_data.iterrows():
        metadata = {attribute: row[column] for attribute, column in columns.items()}
        identity = metadata[key]
        record = records.get(identity)
        if record is None:
            record = model(**metadata)
            session.add(record)
            records[identity] = record
        else:
            for attribute, value in metadata.items():
                setattr(record, attribute, value)


def update_sleeves() -> None:
    """Merge TCG and OCG sleeves while preserving local asset state."""
    datasets = (
        (SleeveModel, get_github_parquet_file("data/sleeves.parquet")),
        (SleeveOcgModel, get_github_parquet_file("data/sleeves_ocg.parquet")),
    )
    for model, remote_data in datasets:
        _merge_metadata(model, remote_data, "bundle", {"bundle": "bundle"})


def update_cards() -> None:
    """Refresh original TCG/OCG card text and indices, keeping saved edits."""
    datasets = (
        (CardModel, get_github_parquet_file("data/cards.parquet")),
        (CardOcgModel, get_github_parquet_file("data/cards_ocg.parquet")),
    )
    for model, remote_data in datasets:
        _merge_metadata(
            model,
            remote_data,
            "bundle",
            {
                "bundle": "bundle",
                "name": "name",
                "description": "description",
                "data_index": "data_index",
            },
        )


def update_faces() -> None:
    """Refresh face names by their asset key, keeping local state."""
    _merge_metadata(
        FaceModel,
        get_github_parquet_file("data/faces.parquet"),
        "key",
        {"key": "key", "name": "name"},
    )


def update_wallpapers() -> None:
    """Refresh wallpaper bundles by name, keeping local state."""
    _merge_metadata(
        WallpaperModel,
        get_github_parquet_file("data/wallpapers.parquet"),
        "name",
        {
            "name": "name",
            "bundle_icon": "icon",
            "bundle_background": "back",
            "bundle_foreground": "front",
        },
    )


def update_fields() -> None:
    """Refresh field orientation metadata by bundle, keeping local state."""
    _merge_metadata(
        FieldModel,
        get_github_parquet_file("data/fields.parquet"),
        "bundle",
        {"bundle": "bundle", "flipped": "flipped", "bottom": "bottom"},
    )


def update_icons() -> None:
    """Refresh player icon bundles by name, keeping local state."""
    _merge_metadata(
        IconModel,
        get_github_parquet_file("data/icons.parquet"),
        "name",
        {
            "name": "name",
            "bundle_small": "small",
            "bundle_medium": "medium",
            "bundle_big": "large",
        },
    )


def update_boxes() -> None:
    """Refresh deck box bundles by name, keeping local state."""
    _merge_metadata(
        DeckBoxModel,
        get_github_parquet_file("data/deck_boxes.parquet"),
        "name",
        {
            "name": "name",
            "small": "small",
            "medium": "medium",
            "o_medium": "o_medium",
            "r_medium": "r_medium",
            "large": "large",
            "o_large": "o_large",
            "r_large": "r_large",
        },
    )


def update_card_metadata() -> None:
    """Refresh metadata file bundles by name, preserving cached file data."""
    _merge_metadata(
        CardMetadataModel,
        get_github_parquet_file("data/metadata.parquet"),
        "name",
        {"name": "name", "bundle": "bundle"},
    )


def update_coins() -> None:
    """Refresh coin bundles by name, keeping local state."""
    _merge_metadata(
        CoinModel,
        get_github_parquet_file("data/coins.parquet"),
        "name",
        {
            "name": "name",
            "bundle_small": "small",
            "bundle_medium": "medium",
            "bundle_big": "large",
        },
    )


def update_card_icons() -> None:
    """Refresh card icon atlas coordinates by name, keeping local state."""
    _merge_metadata(
        CardIconModel,
        get_github_parquet_file("data/card_icons.parquet"),
        "name",
        {"name": "name", "x": "x", "y": "y", "width": "width", "height": "height"},
    )
