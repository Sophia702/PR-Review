from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import metrics
from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import Repo
from app.sync import sync_repo

app = FastAPI(title="PR Review Analytics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


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


@app.post("/sync/{owner}/{repo}")
def trigger_sync(owner: str, repo: str, db: Session = Depends(get_db)) -> dict:
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
