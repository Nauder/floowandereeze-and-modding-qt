"""Regression coverage for updates that must preserve users' asset state."""

import unittest
from unittest.mock import patch

from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import objects

# Importing the models creates their tables. Keep that away from database.db.
with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
    from services import update_service


CASES = (
    (
        "update_sleeves",
        models.SleeveModel,
        "data/sleeves.parquet",
        "bundle",
        {"bundle": "bundle"},
    ),
    (
        "update_sleeves",
        models.SleeveOcgModel,
        "data/sleeves_ocg.parquet",
        "bundle",
        {"bundle": "bundle"},
    ),
    (
        "update_cards",
        models.CardModel,
        "data/cards.parquet",
        "bundle",
        {
            "bundle": "bundle",
            "name": "name",
            "description": "description",
            "data_index": "data_index",
        },
    ),
    (
        "update_cards",
        models.CardOcgModel,
        "data/cards_ocg.parquet",
        "bundle",
        {
            "bundle": "bundle",
            "name": "name",
            "description": "description",
            "data_index": "data_index",
        },
    ),
    (
        "update_faces",
        models.FaceModel,
        "data/faces.parquet",
        "key",
        {"key": "key", "name": "name"},
    ),
    (
        "update_wallpapers",
        models.WallpaperModel,
        "data/wallpapers.parquet",
        "name",
        {
            "name": "name",
            "bundle_icon": "icon",
            "bundle_background": "back",
            "bundle_foreground": "front",
        },
    ),
    (
        "update_fields",
        models.FieldModel,
        "data/fields.parquet",
        "bundle",
        {"bundle": "bundle", "flipped": "flipped", "bottom": "bottom"},
    ),
    (
        "update_icons",
        models.IconModel,
        "data/icons.parquet",
        "name",
        {
            "name": "name",
            "bundle_small": "small",
            "bundle_medium": "medium",
            "bundle_big": "large",
        },
    ),
    (
        "update_boxes",
        models.DeckBoxModel,
        "data/deck_boxes.parquet",
        "name",
        {
            column: column
            for column in (
                "name",
                "small",
                "medium",
                "o_medium",
                "r_medium",
                "large",
                "o_large",
                "r_large",
            )
        },
    ),
    (
        "update_card_metadata",
        models.CardMetadataModel,
        "data/metadata.parquet",
        "name",
        {"name": "name", "bundle": "bundle"},
    ),
    (
        "update_coins",
        models.CoinModel,
        "data/coins.parquet",
        "name",
        {
            "name": "name",
            "bundle_small": "small",
            "bundle_medium": "medium",
            "bundle_big": "large",
        },
    ),
    (
        "update_card_icons",
        models.CardIconModel,
        "data/card_icons.parquet",
        "name",
        {column: column for column in ("name", "x", "y", "width", "height")},
    ),
)


def metadata_values(columns, version):
    """Make distinct valid values for each metadata field."""
    values = {}
    for attribute in columns:
        if attribute in ("key", "data_index", "x", "y", "width", "height"):
            values[attribute] = version
        elif attribute in ("flipped", "bottom"):
            values[attribute] = bool(version % 2)
        else:
            values[attribute] = f"{version}_{attribute}"
    return values


class UpdateServiceTests(unittest.TestCase):
    """Exercise the public update paths against an isolated SQLAlchemy database."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.session_patch = patch.object(update_service, "session", self.session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.session.close()
        self.engine.dispose()

    def test_refresh_preserves_local_state_and_adds_new_assets(self):
        """Refresh all asset types without losing edits, flags, or identities."""
        for function, model, path, key, columns in CASES:
            with self.subTest(model=model.__name__):
                original = metadata_values(columns, 1)
                missing = metadata_values(columns, 2)
                refreshed = metadata_values(columns, 3)
                refreshed[key] = original[key]
                new = metadata_values(columns, 4)
                local = {}
                if issubclass(model, models.UnityAsset):
                    local.update(favorite=True, has_backup=True)
                if model in (models.CardModel, models.CardOcgModel):
                    local.update(
                        modded_name="Saved name", modded_description="Saved text"
                    )
                if model is models.CardMetadataModel:
                    local.update(
                        data=b"raw",
                        data_decoded=b"decoded",
                        data_json='{"saved": true}',
                    )
                existing = model(**original, **local)
                absent = model(**missing, **local)
                self.session.add_all([existing, absent])
                self.session.commit()
                existing_id, absent_id = existing.id, absent.id

                # Extra remote columns must not overwrite fields owned by users.
                rows = [
                    {
                        **{column: values[attr] for attr, column in columns.items()},
                        "favorite": False,
                        "has_backup": False,
                        "modded_name": "remote",
                    }
                    for values in (refreshed, new)
                ]
                remote = DataFrame(rows)
                with patch.object(
                    update_service,
                    "get_github_parquet_file",
                    side_effect=lambda requested, path=path, remote=remote: (
                        remote if requested == path else DataFrame()
                    ),
                ):
                    getattr(update_service, function)()
                    # Repeating before commit must not duplicate pending inserts.
                    getattr(update_service, function)()
                self.session.commit()
                self.session.expire_all()

                self.assertEqual(self.session.query(model).count(), 3)
                self.assertEqual(existing.id, existing_id)
                self.assertEqual(absent.id, absent_id)
                for attribute, value in refreshed.items():
                    self.assertEqual(getattr(existing, attribute), value)
                for attribute, value in missing.items():
                    self.assertEqual(getattr(absent, attribute), value)
                for attribute, value in local.items():
                    self.assertEqual(getattr(existing, attribute), value)
                    self.assertEqual(getattr(absent, attribute), value)
                inserted = self.session.query(model).filter_by(**{key: new[key]}).one()
                for attribute, value in new.items():
                    self.assertEqual(getattr(inserted, attribute), value)
                if issubclass(model, models.UnityAsset):
                    self.assertFalse(inserted.favorite)
                    self.assertFalse(inserted.has_backup)

    def test_empty_download_preserves_records(self):
        """An empty response must never erase saved assets."""
        for function, model, _, _, columns in CASES:
            with self.subTest(model=model.__name__):
                existing = model(**metadata_values(columns, 1))
                self.session.add(existing)
                self.session.commit()
                existing_id = existing.id
                with patch.object(
                    update_service, "get_github_parquet_file", return_value=DataFrame()
                ):
                    getattr(update_service, function)()
                self.session.commit()
                self.assertIs(self.session.get(model, existing_id), existing)


if __name__ == "__main__":
    unittest.main()
