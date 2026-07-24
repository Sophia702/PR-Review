import secrets as secrets_module
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import metrics
from app.auth import get_session_github_token
from app.auth import router as auth_router
from app.config import get_settings
from app.db import Base, engine, get_db
from app.github_client import GitHubClient
from app.models import Repo
from app.scheduler import start_scheduler
from app.sync import sync_repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    scheduler = start_scheduler(settings.sync_interval_minutes) if settings.sync_interval_minutes > 0 else None
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="PR Review Analytics", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins_list,
    allow_credentials=True,  # required for the session cookie to cross origins
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret_key,
    same_site="none",  # frontend and backend are different origins
    https_only=get_settings().session_cookie_secure,
)

app.include_router(auth_router)


def require_sync_auth(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Either a valid X-API-Key or a logged-in GitHub session authorizes a
    sync. The API key stays available for scripts/CI that can't do a browser
    OAuth redirect; the scheduler bypasses this endpoint entirely (it calls
    sync_repo directly), so it's unaffected either way."""
    configured_key = get_settings().sync_api_key
    has_valid_key = bool(configured_key and x_api_key and secrets_module.compare_digest(x_api_key, configured_key))
    has_session = bool(request.session.get("github_login"))
    if not has_valid_key and not has_session:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key, and no active session")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@dataclass
class RepoSummary:
    owner: str
    name: str


@app.get("/repos")
def list_repos(db: Session = Depends(get_db)) -> list[RepoSummary]:
    return [RepoSummary(owner=r.owner, name=r.name) for r in db.query(Repo).order_by(Repo.owner, Repo.name).all()]


@app.post("/sync/{owner}/{repo}", dependencies=[Depends(require_sync_auth)])
def trigger_sync(owner: str, repo: str, request: Request, db: Session = Depends(get_db)) -> dict:
    # sync_repo() only closes a client it created itself (owns_client), so a
    # session-derived client - used to make this sync draw from the logged-in
    # user's own rate limit instead of the shared token - has to be closed here.
    session_token = get_session_github_token(request)
    if session_token:
        with GitHubClient(token=session_token) as client:
            synced = sync_repo(db, owner, repo, client=client)
    else:
        synced = sync_repo(db, owner, repo)
    return {"repo": f"{owner}/{repo}", "synced": synced}


def _get_repo(db: Session, owner: str, repo: str) -> Repo:
    repo_row = db.query(Repo).filter_by(owner=owner, name=repo).one_or_none()
    if repo_row is None:
        raise HTTPException(status_code=404, detail=f"{owner}/{repo} has not been synced yet")
    return repo_row


@app.get("/metrics/{owner}/{repo}/time-to-first-review")
def get_time_to_first_review(
    owner: str,
    repo: str,
    since: datetime | None = None,
    until: datetime | None = None,
    author: str | None = None,
    db: Session = Depends(get_db),
) -> metrics.DurationSummary:
    repo_row = _get_repo(db, owner, repo)
    return metrics.time_to_first_review(db, repo_row.id, since=since, until=until, author=author)


@app.get("/metrics/{owner}/{repo}/time-to-merge")
def get_time_to_merge(
    owner: str,
    repo: str,
    since: datetime | None = None,
    until: datetime | None = None,
    author: str | None = None,
    db: Session = Depends(get_db),
) -> metrics.DurationSummary:
    repo_row = _get_repo(db, owner, repo)
    return metrics.time_to_merge(db, repo_row.id, since=since, until=until, author=author)


@app.get("/metrics/{owner}/{repo}/review-load")
def get_review_load(
    owner: str,
    repo: str,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
) -> list[metrics.ReviewerLoad]:
    repo_row = _get_repo(db, owner, repo)
    return metrics.review_load(db, repo_row.id, since=since, until=until)


@app.get("/metrics/{owner}/{repo}/stale-prs")
def get_stale_prs(
    owner: str,
    repo: str,
    stale_days: int = Query(14, ge=1),
    db: Session = Depends(get_db),
) -> list[metrics.StalePR]:
    repo_row = _get_repo(db, owner, repo)
    return metrics.stale_prs(db, repo_row.id, stale_days=stale_days)


@app.get("/metrics/{owner}/{repo}/review-reciprocity")
def get_review_reciprocity(
    owner: str,
    repo: str,
    min_interactions: int = Query(2, ge=1),
    db: Session = Depends(get_db),
) -> list[metrics.ReciprocityPair]:
    repo_row = _get_repo(db, owner, repo)
    return metrics.review_reciprocity(db, repo_row.id, min_interactions=min_interactions)
