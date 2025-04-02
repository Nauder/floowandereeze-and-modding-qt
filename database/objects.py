"""
Database configuration and session management.
This module sets up SQLAlchemy with SQLite database and provides a global session object.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Create declarative base for model classes
base = declarative_base()

# Create SQLite database engine
engine = create_engine("sqlite:///database.db")

# Create session factory
DBsession = sessionmaker(bind=engine)

# Create global session instance
session = DBsession()
