from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pr_review"
    github_graphql_url: str = "https://api.github.com/graphql"
    backfill_days: int = 180
    cors_allow_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
