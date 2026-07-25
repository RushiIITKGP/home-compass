

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://homecompass:homecompass@localhost:5432/homecompass",
)

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Session:
    """Use as: `session = get_session()` ... `session.close()`,
    or as a context manager: `with get_session() as session: ...`
    (SQLAlchemy's Session supports the context manager protocol directly)."""
    return SessionLocal()
