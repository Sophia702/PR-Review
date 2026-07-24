from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pr_review"
    github_graphql_url: str = "https://api.github.com/graphql"
    backfill_days: int = 180
    # Comma-separated rather than a JSON list — much easier to set via
    # `fly secrets set` / plain shell env vars than a quoted JSON array.
    cors_allow_origins: str = "http://localhost:5173"
    # Required to call POST /sync. Empty means "reject everything" (fail
    # closed) rather than "auth disabled" - an unset key on a deployed
    # instance should never mean the endpoint is silently open.
    sync_api_key: str = ""
    # Background periodic sync of every already-tracked repo. 0 disables it.
    sync_interval_minutes: int = 30

    # GitHub OAuth App credentials (github.com/settings/developers). Lets a
    # logged-in user's own token be used for their sync requests instead of
    # the shared github_token, so a sync draws from their rate limit.
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    # Signs the session cookie (Starlette SessionMiddleware) and the
    # short-lived OAuth `state` param. Generate with secrets.token_urlsafe(32).
    session_secret_key: str = ""
    # Fernet key (44-char urlsafe-base64) encrypting the GitHub token stored
    # inside the session cookie, on top of the cookie's own signature.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    session_encryption_key: str = ""
    # SameSite=None session cookies (required since frontend and backend are
    # different origins) are only honored by browsers over HTTPS. Set false
    # for local http:// dev.
    session_cookie_secure: bool = True
    frontend_url: str = "http://localhost:5173"
    backend_public_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
