import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.models import Repo
from app.sync import sync_repo

logger = logging.getLogger(__name__)


def sync_all_repos() -> None:
    """Incrementally re-sync every repo already tracked in the DB.

    Each repo gets its own session/transaction so one repo's sync failure
    (e.g. a rate limit or a since-deleted repo) can't poison the others in
    the same run.
    """
    db = SessionLocal()
    try:
        repo_keys = [(r.owner, r.name) for r in db.query(Repo).all()]
    finally:
        db.close()

    for owner, name in repo_keys:
        db = SessionLocal()
        try:
            synced = sync_repo(db, owner, name)
            logger.info("periodic sync: %s/%s (%d PRs touched)", owner, name, synced)
        except Exception:
            db.rollback()
            logger.exception("periodic sync failed for %s/%s", owner, name)
        finally:
            db.close()


def start_scheduler(interval_minutes: int) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_all_repos, "interval", minutes=interval_minutes, id="sync_all_repos")
    scheduler.start()
    return scheduler
