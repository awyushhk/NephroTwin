"""PostgreSQL configuration and SQLAlchemy session management for renal twin."""
import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(Path(__file__).with_name(".env"), override=False)


class Base(DeclarativeBase):
    pass


def database_url() -> URL:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required for Renal Digital Twin. Copy api/.env.example to api/.env and configure PostgreSQL.")
    try:
        url = make_url(value)
    except Exception as exc:
        raise RuntimeError("DATABASE_URL is invalid. Use a PostgreSQL URL such as postgresql+psycopg://user:password@localhost:5432/renal_twin.") from exc
    if url.get_backend_name() not in {"postgresql"}:
        raise RuntimeError("Renal Digital Twin requires PostgreSQL; DATABASE_URL must use the postgresql+psycopg driver.")
    return url


@lru_cache(maxsize=1)
def make_session_factory():
    engine = create_engine(database_url(), pool_pre_ping=True, future=True)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    try:
        _, factory = make_session_factory()
        with factory() as session:
            yield session
    except SQLAlchemyError as exc:
        raise RuntimeError("PostgreSQL is unavailable. Check DATABASE_URL, that PostgreSQL is running, and that migrations are applied.") from exc
    except RuntimeError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def verify_database():
    engine, _ = make_session_factory()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise RuntimeError("PostgreSQL connectivity check failed. Start PostgreSQL and verify DATABASE_URL credentials, host, and port.") from exc
    finally:
        engine.dispose()
