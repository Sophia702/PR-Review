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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
