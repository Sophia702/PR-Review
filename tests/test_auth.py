from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from itsdangerous import BadSignature, SignatureExpired

import app.auth as auth_module
from test_sync import GRAPHQL_URL, _pr_node, _search_response

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def test_state_round_trips():
    serializer = auth_module._state_serializer()
    state = serializer.dumps({"nonce": "abc", "return_to": "http://localhost:5173"})

    payload = serializer.loads(state, max_age=600)

    assert payload == {"nonce": "abc", "return_to": "http://localhost:5173"}


def test_state_rejects_tampering():
    serializer = auth_module._state_serializer()
    state = serializer.dumps({"nonce": "abc", "return_to": "http://localhost:5173"})
    tampered = state[:-1] + ("x" if state[-1] != "x" else "y")

    with pytest.raises(BadSignature):
        serializer.loads(tampered, max_age=600)


def test_state_rejects_expiry():
    serializer = auth_module._state_serializer()
    state = serializer.dumps({"nonce": "abc", "return_to": "http://localhost:5173"})

    with pytest.raises(SignatureExpired):
        serializer.loads(state, max_age=-1)


def test_me_is_null_when_logged_out(client):
    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"github_login": None}


def _extract_state(login_redirect_url: str) -> str:
    query = parse_qs(urlparse(login_redirect_url).query)
    return query["state"][0]


@respx.mock
def test_login_callback_sets_session_and_me_reflects_it(client):
    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "gho_faketoken", "token_type": "bearer", "scope": ""})
    )
    respx.get(GITHUB_USER_URL).mock(return_value=httpx.Response(200, json={"login": "octocat", "id": 1}))

    login_response = client.get("/auth/github/login", follow_redirects=False)
    state = _extract_state(login_response.headers["location"])

    callback_response = client.get(
        f"/auth/github/callback?code=fake_code&state={state}", follow_redirects=False
    )
    assert callback_response.status_code in (302, 307)

    me_response = client.get("/auth/me")
    assert me_response.json() == {"github_login": "octocat"}


@respx.mock
def test_sync_accepts_session_with_no_api_key(client):
    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "gho_faketoken", "token_type": "bearer", "scope": ""})
    )
    respx.get(GITHUB_USER_URL).mock(return_value=httpx.Response(200, json={"login": "octocat", "id": 1}))
    graphql_route = respx.post(GRAPHQL_URL).mock(
        return_value=_search_response([_pr_node(1, "PR_1", "2020-01-01T00:00:00Z")])
    )

    login_response = client.get("/auth/github/login", follow_redirects=False)
    state = _extract_state(login_response.headers["location"])
    client.get(f"/auth/github/callback?code=fake_code&state={state}", follow_redirects=False)

    response = client.post("/sync/acme/widgets")

    assert response.status_code == 200
    assert graphql_route.calls[0].request.headers["authorization"] == "Bearer gho_faketoken"


def test_logout_clears_session(client):
    client.post("/auth/logout")

    assert client.get("/auth/me").json() == {"github_login": None}
