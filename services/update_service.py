"""
This module provides functionality to update the database with the latest data from the remote
source.
"""

import requests
from requests.exceptions import RequestException, Timeout, HTTPError
from pandas import read_parquet, DataFrame, isna
from pandas.errors import EmptyDataError

from database.models import (
    AppConfig,
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
from util.metadata_source import (
    DEFAULT_METADATA_REPOSITORY,
    DEFAULT_METADATA_BRANCH,
    normalize_metadata_source,
)


def _github_source(owner=None, repo=None, branch=None):
    """Read persisted settings for version text and every metadata dataset."""
    config = session.query(AppConfig).first()
    repository, selected_branch = normalize_metadata_source(
        getattr(config, "metadata_repository", None) or DEFAULT_METADATA_REPOSITORY,
        getattr(config, "metadata_branch", None) or DEFAULT_METADATA_BRANCH,
    )
    selected_owner, selected_repo = repository.split("/")
    owner = selected_owner if owner is None else owner
    repo = selected_repo if repo is None else repo
    _, branch = normalize_metadata_source(
        f"{owner}/{repo}", selected_branch if branch is None else branch
    )
    return owner, repo, {"ref": branch} if branch else {}


def get_github_raw_file(path: str, owner=None, repo=None, branch=None) -> str:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.
    :param branch: Branch/ref override; blank follows the repository default.
        Omitted source arguments use saved Configuration settings.

    :return: The raw content of the file.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    """
    owner, repo, params = _github_source(owner, repo, branch)
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        # Send a GET request to fetch file metadata
        response = requests.get(url, headers=headers, params=params, timeout=10)
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
        raise HTTPError(
            f"GitHub API request failed: {str(e)}", response=e.response
        ) from e
    except RequestException as e:
        raise RequestException(f"Request failed: {str(e)}") from e


def get_github_parquet_file(path: str, owner=None, repo=None, branch=None) -> DataFrame:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.
    :param branch: Branch/ref override; blank follows the repository default.
        Omitted source arguments use saved Configuration settings.

    :return: The raw content of the file as a pandas DataFrame.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    :raises EmptyDataError: If the parquet file is empty or invalid
    """
    owner, repo, params = _github_source(owner, repo, branch)
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        # Send a GET request to fetch file metadata
        response = requests.get(url, headers=headers, params=params, timeout=10)
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
        raise HTTPError(
            f"GitHub API request failed: {str(e)}", response=e.response
        ) from e
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
        if hasattr(model, "display_name"):
            column = (
                "name" if model in (SleeveModel, SleeveOcgModel) else "display_name"
            )
            if column in remote_data.columns:
                value = row[column]
                metadata["display_name"] = None if isna(value) else value
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


def update_summon_animations(remote_data=None, db_session=None) -> bool:
    """Atomically merge composite identities without touching local edit records.

    A missing optional ETL file is supported; malformed existing data is an error.
    The caller owns the outer transaction, like other metadata refresh functions.
    """
    from database.models import SummonAnimationAssetModel
    from unity.summon_metadata import COLUMNS, identity, validate_row

    target = db_session if db_session is not None else session
    if remote_data is None:
        try:
            remote_data = get_github_parquet_file("data/summon_animations.parquet")
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return False
            raise
    if set(COLUMNS) - set(remote_data.columns):
        raise ValueError("Summon animation dataset has missing columns.")
    rows, seen = [], set()
    for values in remote_data.to_dict("records"):
        row = validate_row({k: None if isna(values[k]) else values[k] for k in COLUMNS})
        key = identity(row)
        if key in seen:
            raise ValueError("Duplicate summon component identity in dataset.")
        seen.add(key)
        rows.append(row)
    connection = target.connection()
    if (
        connection.dialect.name == "sqlite"
        and not connection.connection.driver_connection.in_transaction
    ):
        # SQLite otherwise commits an outermost SAVEPOINT on release.
        connection.exec_driver_sql("BEGIN")
    with target.begin_nested():
        records = {
            identity({k: getattr(record, k) for k in COLUMNS}): record
            for record in target.query(SummonAnimationAssetModel).all()
        }
        for row in rows:
            record = records.get(identity(row))
            if record is None:
                target.add(SummonAnimationAssetModel(**row))
            else:
                for key, value in row.items():
                    setattr(record, key, value)
    return True
