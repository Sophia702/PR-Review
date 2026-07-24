import os

from cryptography.fernet import Fernet

# app.main configures SessionMiddleware once at first import (module-level
# code), so these have to be valid before any test file imports app.main -
# setting them here, at conftest module level, guarantees that regardless of
# which test file happens to trigger that first import.
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key")
os.environ.setdefault("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db import Base

TEST_API_KEY = "test-sync-key"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(monkeypatch):
    # Fail-closed by default (empty key), so tests that want the endpoint to
    # succeed opt in explicitly; also disables the background scheduler so
    # tests don't spawn threads that outlive them.
    monkeypatch.setenv("SYNC_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("SYNC_INTERVAL_MINUTES", "0")

    from app.config import get_settings

    get_settings.cache_clear()

    import app.main as main_module

    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(main_module, "engine", test_engine)

    test_session_local = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = test_session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[main_module.get_db] = override_get_db

    # https:// base_url (not the http:// default) so the session cookie's
    # Secure attribute - required alongside SameSite=None, and left on in
    # tests deliberately rather than loosened, since that's the real
    # production setting - actually gets stored/sent by the client's cookie
    # jar between requests.
    with TestClient(main_module.app, base_url="https://testserver") as c:
        yield c

    main_module.app.dependency_overrides.clear()
    get_settings.cache_clear()
