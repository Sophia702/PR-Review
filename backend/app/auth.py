from __future__ import annotations

import secrets as secrets_module
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

_STATE_MAX_AGE_SECONDS = 600


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret_key, salt="oauth-state")


def _fernet() -> Fernet:
    return Fernet(get_settings().session_encryption_key.encode())


@router.get("/github/login")
def github_login(return_to: str | None = None) -> RedirectResponse:
    """Kick off the OAuth handshake. `state` is a signed, time-limited token
    (not a server-side session) carrying a CSRF nonce and the post-login
    redirect target - GitHub round-trips it verbatim, and the callback just
    re-verifies the signature, so nothing needs to be persisted between the
    redirect out and the redirect back."""
    settings = get_settings()
    nonce = secrets_module.token_urlsafe(16)
    state = _state_serializer().dumps({"nonce": nonce, "return_to": return_to or settings.frontend_url})

    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": f"{settings.backend_public_url}/auth/github/callback",
        "scope": "",  # public-repo GraphQL reads need no scope at all
        "state": state,
    }
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/github/callback")
def github_callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = get_settings()
    try:
        payload = _state_serializer().loads(state, max_age=_STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc

    token_response = httpx.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret,
            "code": code,
            "redirect_uri": f"{settings.backend_public_url}/auth/github/callback",
        },
        timeout=30.0,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub did not return an access token")

    user_response = httpx.get(
        GITHUB_USER_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=30.0,
    )
    user_response.raise_for_status()
    github_login_name = user_response.json()["login"]

    request.session["github_login"] = github_login_name
    request.session["encrypted_token"] = _fernet().encrypt(access_token.encode()).decode()

    return RedirectResponse(payload["return_to"])


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "ok"}


@router.get("/me")
def me(request: Request) -> dict:
    return {"github_login": request.session.get("github_login")}


def get_session_github_token(request: Request) -> str | None:
    encrypted = request.session.get("encrypted_token")
    if not encrypted:
        return None
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None
