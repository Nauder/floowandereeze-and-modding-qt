import requests

from sqlalchemy import update

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
from pandas import read_parquet, DataFrame


def get_github_raw_file(
    path: str, owner="Nauder", repo="floowandereeze-and-modding-etl"
) -> str:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.

    :return: The raw content of the file.
    """
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    # Send a GET request to fetch file metadata
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        file_data = response.json()

        # Extract the download URL from the response
        if "download_url" in file_data:
            raw_url = file_data["download_url"]

            # Send a second GET request to fetch the raw file content
            raw_response = requests.get(raw_url, headers=headers)

            if raw_response.status_code == 200:
                return raw_response.text  # Return the raw content of the file
            else:
                raise Exception(
                    f"Failed to download raw file: {raw_response.status_code}"
                )
        else:
            raise Exception("No download URL found in the response.")
    else:
        raise Exception(f"Failed to fetch file metadata: {response.status_code}")


def get_github_parquet_file(
    path: str, owner="Nauder", repo="floowandereeze-and-modding-etl"
) -> DataFrame:
    """
    Fetch a raw file from a private GitHub repository using GitHub REST API.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.

    :return: The raw content of the file.
    """
    # GitHub API URL for repository contents
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Headers for authentication
    headers = {"Accept": "application/vnd.github.v3+json"}

    # Send a GET request to fetch file metadata
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        file_data = response.json()

        # Extract the download URL from the response
        if "download_url" in file_data:
            raw_url = file_data["download_url"]

            return read_parquet(raw_url)
        else:
            raise Exception("No download URL found in the response.")
    else:
        raise Exception(f"Failed to fetch file metadata: {response.status_code}")


def update_sleeves():
    remote_sleeves = get_github_parquet_file("data/sleeves.parquet")
    local_sleeves = [sleeve.bundle for sleeve in session.query(SleeveModel).all()]

    session.add_all(
        [
            SleeveModel(bundle=sleeve)
            for sleeve in remote_sleeves["bundle"]
            if sleeve not in local_sleeves
        ]
    )


def update_cards():
    remote_cards = get_github_parquet_file("data/cards.parquet")
    local_cards = [card.bundle for card in session.query(CardModel).all()]

    session.add_all(
        [
            CardModel(
                bundle=card["bundle"],
                name=card["name"],
                description=card["description"],
                data_index=card["data_index"],
            )
            for _, card in remote_cards.iterrows()
            if card["bundle"] not in local_cards
        ]
    )


def update_faces():
    remote_faces = get_github_parquet_file("data/faces.parquet")
    local_faces = session.query(FaceModel).all()

    if local_faces:
        for _, face in remote_faces.iterrows():
            update_statement = (
                update(FaceModel)
                .where(FaceModel.name == face["name"], FaceModel.key != face["key"])
                .values(key=face["key"])
            )
            session.execute(update_statement)
            session.commit()
    else:
        session.add_all(
            FaceModel(key=face["key"], name=face["name"])
            for _, face in remote_faces.iterrows()
        )


def update_wallpapers():
    remote_wallpapers = get_github_parquet_file("data/wallpapers.parquet")
    local_wallpapers = [
        wallpaper.name for wallpaper in session.query(WallpaperModel).all()
    ]

    session.add_all(
        [
            WallpaperModel(
                name=wallpaper["name"],
                bundle_icon=wallpaper["icon"],
                bundle_background=wallpaper["back"],
                bundle_foreground=wallpaper["front"],
            )
            for _, wallpaper in remote_wallpapers.iterrows()
            if wallpaper["name"] not in local_wallpapers
        ]
    )


def update_fields():
    remote_fields = get_github_parquet_file("data/fields.parquet")
    local_fields = [field.bundle for field in session.query(FieldModel).all()]

    session.add_all(
        [
            FieldModel(
                bundle=field["bundle"], flipped=field["flipped"], bottom=field["bottom"]
            )
            for _, field in remote_fields.iterrows()
            if field["bundle"] not in local_fields
        ]
    )


def update_icons():
    remote_icons = get_github_parquet_file("data/icons.parquet")
    local_icons = [icon.name for icon in session.query(IconModel).all()]

    session.add_all(
        [
            IconModel(
                name=icon["name"],
                bundle_small=icon["small"],
                bundle_medium=icon["medium"],
                bundle_big=icon["large"],
            )
            for _, icon in remote_icons.iterrows()
            if icon["name"] not in local_icons
        ]
    )


def update_boxes():
    remote_boxes = get_github_parquet_file("data/deck_boxes.parquet")

    local_boxes = [box.name for box in session.query(DeckBoxModel).all()]

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
            if box["name"] not in local_boxes
        ]
    )


def update_card_metadata():
    remote_data = get_github_parquet_file("data/metadata.parquet")
    local_data = [data.name for data in session.query(CardMetadataModel).all()]

    session.add_all(
        [
            CardMetadataModel(name=data["name"], bundle=data["bundle"])
            for _, data in remote_data.iterrows()
            if data["name"] not in local_data
        ]
    )
