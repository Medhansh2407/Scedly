"""
Database connection setup.

The connection string is read from the DATABASE_URL environment variable.
Set this in a .env file at the project root (never commit it).

Example .env:
    DATABASE_URL=postgresql://user:pass@localhost:5432/calendar
"""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine

# Load optional personal-use overrides first. These files are ignored by Git
# and contain only local configuration, never credentials.
load_dotenv('.env.local', override=False)
load_dotenv('.env', override=False)

# Required: the database connection string.
# We fail loudly if it isn't set so we never accidentally run against the wrong DB.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to your .env file (see .env.example)."
    )

# The engine is the connection pool. Created once, reused forever.
# echo=True prints every SQL statement to the console -- useful while learning.
engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    """
    Create all tables defined in SQLModel models.
    
    Called once at app startup. Safe to call multiple times -- it only
    creates tables that don't already exist.
    """
    # Importing here ensures all models are registered with SQLModel.metadata
    # before we ask it to create the tables.
    from app.models import models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """
    Return a new database session.
    
    A session is a "conversation" with the database -- you open it, run queries,
    commit changes, then close it. CRUD functions accept a Session as their
    first argument so the caller controls the transaction lifecycle.
    """
    return Session(engine)


def get_session_dependency() -> Generator[Session, None, None]:
    """Yield a request-scoped session and always close it after the response."""
    with Session(engine) as session:
        yield session
