import respx

from conftest import TEST_API_KEY
from test_sync import GRAPHQL_URL, _pr_node, _search_response


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
