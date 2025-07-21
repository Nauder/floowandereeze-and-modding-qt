"""
Database migration utilities for handling schema changes between versions.
This module ensures that database schema changes are applied automatically
when users update to a new version of the application.
"""

import sqlite3
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def get_columns(cursor, table_name: str) -> List[str]:
    """Get list of column names for a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [column[1] for column in cursor.fetchall()]


def run_migrations(db_path: str = "database.db") -> None:
    """
    Run all necessary database migrations.

    This function checks the current database schema and applies
    any missing migrations to bring it up to the latest version.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Migration 1: Add background_mode column to app_config
        columns = get_columns(cursor, "app_config")
        if "background_mode" not in columns:
            logger.info("Migrating database: Adding background_mode column")
            cursor.execute(
                "ALTER TABLE app_config ADD COLUMN background_mode VARCHAR(10) DEFAULT 'stretched'"
            )
            conn.commit()
            logger.info("Migration completed: background_mode column added")

        # Add future migrations here following the same pattern
        # Migration 2: Example for future use
        # if "some_future_column" not in get_columns(cursor, "some_table"):
        #     cursor.execute("ALTER TABLE some_table ADD COLUMN some_future_column ...")
        #     conn.commit()

        conn.close()
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        if "conn" in locals():
            conn.close()
        # Don't re-raise the exception - we want the app to continue even if migration fails
        # The user might not be able to use new features, but at least the app will run
