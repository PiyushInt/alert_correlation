import uuid
from collections.abc import Generator
from typing import Any

import psycopg
import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from ace.config import settings
from alembic import command


@pytest.fixture(scope="session")
def engine() -> Any:
    # Read the base URL and create a test DB name
    base_url = settings.DATABASE_URL
    test_db_name = f"test_ace_{uuid.uuid4().hex[:8]}"

    # We must connect to an existing database (like 'postgres' or 'ace_db') to create the new one
    # Replace the DB name in the URL to connect to the default 'postgres' database
    url_parts = base_url.rsplit("/", 1)
    admin_url = f"{url_parts[0]}/postgres"

    # Create the database
    # We must use raw psycopg for this because SQLAlchemy cannot easily do this without autocommit
    conn_info = admin_url.replace("+psycopg", "")
    with psycopg.connect(conn_info, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {test_db_name}")

    # The URL for the test database
    test_db_url = f"{url_parts[0]}/{test_db_name}"

    # Run migrations
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_db_url, poolclass=NullPool)
    yield engine

    engine.dispose()

    # Drop the database
    with psycopg.connect(conn_info, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Drop active connections
            cur.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{test_db_name}' AND pid <> pg_backend_pid()"
            )
            cur.execute(f"DROP DATABASE {test_db_name}")


@pytest.fixture
def db_session(engine: Any) -> Generator[Session, None, None]:
    """
    Returns an sqlalchemy session, and after the test tears down everything.
    Runs inside a transaction that is rolled back so tests are isolated.
    """
    connection = engine.connect()
    # begin a non-ORM transaction
    transaction = connection.begin()

    # bind an individual Session to the connection
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()
