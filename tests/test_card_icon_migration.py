"""Card icon upgrades preserve local state and allow metadata refreshes."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import objects
from database.migrations import run_migrations

with patch.object(objects, "engine", create_engine("sqlite:///:memory:")):
    from database import models
    from services import update_service


class CardIconMigrationTests(unittest.TestCase):
    """Exercise legacy, partially upgraded and current databases."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "database.db"
        self.engine = create_engine("sqlite:///" + self.path.as_posix())
        self.addCleanup(self.engine.dispose)
        objects.base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.session.close)
        self.session.add(models.AppConfig(version="2026-09-29"))
        self.session.commit()

    def legacy_table(self, extra_columns=""):
        """Recreate the pre-atlas schema, optionally with a partial upgrade."""
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE card_icon")
            connection.exec_driver_sql(
                "CREATE TABLE card_icon ("
                "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
                "favorite BOOLEAN NOT NULL, has_backup BOOLEAN NOT NULL"
                + extra_columns
                + ")"
            )
            connection.exec_driver_sql(
                "INSERT INTO card_icon (id, name, favorite, has_backup) "
                "VALUES (7, 'GUI_T_Icon1_Limit00', 1, 1)"
            )

    def test_legacy_upgrade_and_refresh_preserve_local_state(self):
        """Upgraded records can be queried, refreshed and inserted safely."""
        self.legacy_table()
        run_migrations(str(self.path))
        self.session.expire_all()
        icon = self.session.query(models.CardIconModel).one()
        self.assertEqual((icon.width, icon.height, icon.x, icon.y), (0, 0, 0, 0))
        self.assertIsNone(self.session.query(models.AppConfig).one().version)

        row = {"name": icon.name, "width": 63.8, "height": 63.8, "x": 355.0, "y": 620.0}
        with (
            patch.object(update_service, "session", self.session),
            patch.object(
                update_service, "get_github_parquet_file", return_value=DataFrame([row])
            ),
        ):
            update_service.update_card_icons()
        self.session.commit()
        self.assertEqual(icon.id, 7)
        self.assertTrue(icon.favorite)
        self.assertTrue(icon.has_backup)
        self.assertEqual((icon.width, icon.height, icon.x, icon.y), (63.8, 63.8, 355, 620))

        self.session.add(
            models.CardIconModel(name="new", width=64, height=64, x=0, y=0)
        )
        self.session.commit()
        self.assertEqual(self.session.query(models.CardIconModel).count(), 2)

    def test_partial_upgrade_preserves_existing_coordinates(self):
        """Only missing coordinates receive placeholder values."""
        self.legacy_table(", width INTEGER NOT NULL DEFAULT 64, x INTEGER DEFAULT 123")
        run_migrations(str(self.path))
        icon = self.session.query(models.CardIconModel).one()
        self.assertEqual((icon.width, icon.height, icon.x, icon.y), (64, 0, 123, 0))
        self.assertTrue(icon.favorite and icon.has_backup)

    def test_rerun_preserves_refreshed_version_and_coordinates(self):
        """Subsequent startups retain downloaded coordinates and version."""
        self.legacy_table()
        run_migrations(str(self.path))
        config = self.session.query(models.AppConfig).one()
        config.version = "2026-10-25"
        icon = self.session.query(models.CardIconModel).one()
        icon.width, icon.height, icon.x, icon.y = 64, 65, 100, 200
        self.session.commit()
        run_migrations(str(self.path))
        self.session.expire_all()
        self.assertEqual(config.version, "2026-10-25")
        self.assertEqual((icon.width, icon.height, icon.x, icon.y), (64, 65, 100, 200))

    def test_current_schema_does_not_force_refresh(self):
        """Current databases do not need an extra metadata download."""
        run_migrations(str(self.path))
        self.session.expire_all()
        self.assertEqual(self.session.query(models.AppConfig).one().version, "2026-09-29")
