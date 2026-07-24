import httpx
import pytest
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from test_sync import GRAPHQL_URL, _pr_node, _search_response

TEST_API_KEY = "test-sync-key"


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

    with TestClient(main_module.app) as c:
        yield c

    main_module.app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_sync_rejects_missing_api_key(client):
    response = client.post("/sync/acme/widgets")
    assert response.status_code == 401


def test_sync_rejects_wrong_api_key(client):
    response = client.post("/sync/acme/widgets", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


@respx.mock
def test_sync_accepts_correct_api_key(client):
    respx.post(GRAPHQL_URL).mock(return_value=_search_response([_pr_node(1, "PR_1", "2020-01-01T00:00:00Z")]))

    response = client.post("/sync/acme/widgets", headers={"X-API-Key": TEST_API_KEY})

    assert response.status_code == 200
    assert response.json() == {"repo": "acme/widgets", "synced": 1}


def test_health_and_repos_do_not_require_api_key(client):
    assert client.get("/health").status_code == 200
    assert client.get("/repos").status_code == 200
