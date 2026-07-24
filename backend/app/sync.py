from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.github_client import GitHubClient
from app.models import Commit, PullRequest, Repo, Review, ReviewComment, SyncState, User
from app.utils import ensure_utc

_STATE_MAP = {"OPEN": "open", "CLOSED": "closed", "MERGED": "merged"}


def get_or_create_repo(db: Session, owner: str, name: str) -> Repo:
    repo = db.query(Repo).filter_by(owner=owner, name=name).one_or_none()
    if repo is None:
        repo = Repo(owner=owner, name=name)
        db.add(repo)
        db.flush()
    return repo


def upsert_user(db: Session, actor: dict | None) -> User | None:
    """Upsert an author/reviewer/commenter. GitHub's `__typename` tells us bots
    (e.g. dependabot[bot]) apart from humans, so downstream metrics can exclude
    them without guessing from the login string."""
    if actor is None or not actor.get("login"):
        return None
    login = actor["login"]
    is_bot = actor.get("__typename") == "Bot"
    user = db.query(User).filter_by(login=login).one_or_none()
    if user is None:
        user = User(login=login, is_bot=is_bot)
        db.add(user)
        db.flush()
    elif user.is_bot != is_bot:
        user.is_bot = is_bot
    return user


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def upsert_pull_request(db: Session, repo: Repo, node: dict) -> PullRequest:
    author = upsert_user(db, node.get("author"))
    pr = db.query(PullRequest).filter_by(github_id=node["id"]).one_or_none()
    if pr is None:
        pr = PullRequest(github_id=node["id"], repo_id=repo.id, number=node["number"])
        db.add(pr)

    pr.title = node["title"]
    pr.state = _STATE_MAP.get(node["state"], node["state"].lower())
    pr.is_draft = node["isDraft"]
    pr.author_id = author.id if author else None
    pr.created_at = _parse_dt(node["createdAt"])
    pr.updated_at = _parse_dt(node["updatedAt"])
    pr.merged_at = _parse_dt(node.get("mergedAt"))
    pr.closed_at = _parse_dt(node.get("closedAt"))
    db.flush()

    for review_node in node.get("reviews", {}).get("nodes", []):
        upsert_review(db, pr, review_node)

    for thread in node.get("reviewThreads", {}).get("nodes", []):
        for comment_node in thread.get("comments", {}).get("nodes", []):
            upsert_review_comment(db, pr, comment_node)

    for commit_node in node.get("commits", {}).get("nodes", []):
        upsert_commit(db, pr, commit_node)

    return pr


def upsert_review(db: Session, pr: PullRequest, node: dict) -> Review:
    reviewer = upsert_user(db, node.get("author"))
    review = db.query(Review).filter_by(github_id=node["id"]).one_or_none()
    if review is None:
        review = Review(github_id=node["id"], pull_request_id=pr.id)
        db.add(review)
    review.reviewer_id = reviewer.id if reviewer else None
    review.state = node["state"]
    review.submitted_at = _parse_dt(node.get("submittedAt"))
    db.flush()
    return review


def upsert_review_comment(db: Session, pr: PullRequest, node: dict) -> ReviewComment:
    author = upsert_user(db, node.get("author"))
    comment = db.query(ReviewComment).filter_by(github_id=node["id"]).one_or_none()
    if comment is None:
        comment = ReviewComment(github_id=node["id"], pull_request_id=pr.id)
        db.add(comment)
    comment.author_id = author.id if author else None
    comment.created_at = _parse_dt(node["createdAt"])
    db.flush()
    return comment


def upsert_commit(db: Session, pr: PullRequest, node: dict) -> Commit:
    commit_data = node["commit"]
    author = upsert_user(db, commit_data.get("author", {}).get("user"))
    commit = db.query(Commit).filter_by(github_id=commit_data["oid"]).one_or_none()
    if commit is None:
        commit = Commit(github_id=commit_data["oid"], pull_request_id=pr.id)
        db.add(commit)
    commit.author_id = author.id if author else None
    commit.message = commit_data["message"]
    commit.committed_at = _parse_dt(commit_data["committedDate"])
    db.flush()
    return commit


def sync_repo(db: Session, owner: str, name: str, client: GitHubClient | None = None) -> int:
    """Incrementally sync a repo's PRs, reviews, review comments, and commits.

    Resumes from the repo's SyncState cursor (max PR `updatedAt` seen so far)
    instead of re-pulling full history on every run. First run falls back to
    a `backfill_days` window.
    """
    settings = get_settings()
    owns_client = client is None
    client = client or GitHubClient()
    repo = get_or_create_repo(db, owner, name)
    sync_state = db.query(SyncState).filter_by(repo_id=repo.id).one_or_none()

    since = (
        ensure_utc(sync_state.last_synced_at)
        if sync_state and sync_state.last_synced_at
        else datetime.now(timezone.utc) - timedelta(days=settings.backfill_days)
    )

    search_query = f"repo:{owner}/{name} is:pr updated:>={since.strftime('%Y-%m-%dT%H:%M:%S')}"

    max_updated_at = since
    synced_count = 0
    after = None

    try:
        while True:
            page = client.search_pull_requests(search_query, after=after)
            for node in page["nodes"]:
                upsert_pull_request(db, repo, node)
                synced_count += 1
                updated_at = _parse_dt(node["updatedAt"])
                if updated_at and updated_at > max_updated_at:
                    max_updated_at = updated_at

            page_info = page["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]
    finally:
        if owns_client:
            client.close()

    if sync_state is None:
        sync_state = SyncState(repo_id=repo.id)
        db.add(sync_state)
    sync_state.last_synced_at = max_updated_at
    db.commit()

    return synced_count
