from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean, median

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models import PullRequest, Review, User
from app.utils import ensure_utc


@dataclass
class PRDuration:
    number: int
    title: str
    author: str | None
    start_at: datetime
    end_at: datetime
    hours: float


@dataclass
class DurationSummary:
    count: int
    avg_hours: float | None
    median_hours: float | None
    items: list[PRDuration]


@dataclass
class ReviewerLoad:
    reviewer: str
    review_count: int


@dataclass
class StalePR:
    number: int
    title: str
    author: str | None
    updated_at: datetime
    days_stale: int


def _duration_summary(rows) -> DurationSummary:
    items = []
    hours_list = []
    for pr, author_login, end_at in rows:
        start_at = ensure_utc(pr.created_at)
        end_at = ensure_utc(end_at)
        hours = (end_at - start_at).total_seconds() / 3600
        items.append(PRDuration(pr.number, pr.title, author_login, start_at, end_at, hours))
        hours_list.append(hours)
    return DurationSummary(
        count=len(items),
        avg_hours=mean(hours_list) if hours_list else None,
        median_hours=median(hours_list) if hours_list else None,
        items=items,
    )


def time_to_first_review(
    db: Session,
    repo_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
    author: str | None = None,
) -> DurationSummary:
    """PR opened -> earliest non-bot review submitted.

    Draft PRs are excluded: GitHub's GraphQL API has no `readyForReviewAt`
    scalar (it's a timeline event), so we don't yet track when a draft became
    reviewable. Using `created_at` for drafts would understate the metric.
    """
    first_review = (
        select(Review.pull_request_id, func.min(Review.submitted_at).label("first_review_at"))
        .join(User, Review.reviewer_id == User.id)
        .where(User.is_bot.is_(False), Review.submitted_at.isnot(None))
        .group_by(Review.pull_request_id)
        .subquery()
    )

    author_alias = aliased(User)
    query = (
        select(PullRequest, author_alias.login, first_review.c.first_review_at)
        .join(first_review, first_review.c.pull_request_id == PullRequest.id)
        .outerjoin(author_alias, PullRequest.author_id == author_alias.id)
        .where(PullRequest.repo_id == repo_id, PullRequest.is_draft.is_(False))
    )
    if since:
        query = query.where(PullRequest.created_at >= since)
    if until:
        query = query.where(PullRequest.created_at <= until)
    if author:
        query = query.where(author_alias.login == author)

    return _duration_summary(db.execute(query).all())


def time_to_merge(
    db: Session,
    repo_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
    author: str | None = None,
) -> DurationSummary:
    """PR opened -> merged. Closed-without-merge PRs are excluded."""
    author_alias = aliased(User)
    query = (
        select(PullRequest, author_alias.login, PullRequest.merged_at)
        .outerjoin(author_alias, PullRequest.author_id == author_alias.id)
        .where(PullRequest.repo_id == repo_id, PullRequest.merged_at.isnot(None))
    )
    if since:
        query = query.where(PullRequest.created_at >= since)
    if until:
        query = query.where(PullRequest.created_at <= until)
    if author:
        query = query.where(author_alias.login == author)

    return _duration_summary(db.execute(query).all())


def review_load(
    db: Session,
    repo_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ReviewerLoad]:
    """Reviews given per person, to spot one person reviewing everything. Bot
    reviewers (e.g. CI accounts) are excluded so they don't dilute the count."""
    query = (
        select(User.login, func.count(Review.id))
        .select_from(Review)
        .join(User, Review.reviewer_id == User.id)
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .where(
            PullRequest.repo_id == repo_id,
            User.is_bot.is_(False),
            Review.submitted_at.isnot(None),
        )
        .group_by(User.login)
        .order_by(func.count(Review.id).desc())
    )
    if since:
        query = query.where(Review.submitted_at >= since)
    if until:
        query = query.where(Review.submitted_at <= until)

    return [ReviewerLoad(reviewer=login, review_count=count) for login, count in db.execute(query).all()]


def stale_prs(
    db: Session,
    repo_id: int,
    stale_days: int = 14,
    now: datetime | None = None,
) -> list[StalePR]:
    """Open PRs with no activity in more than `stale_days`."""
    now = ensure_utc(now) if now else datetime.now(timezone.utc)
    threshold = now - timedelta(days=stale_days)

    author_alias = aliased(User)
    query = (
        select(PullRequest, author_alias.login)
        .outerjoin(author_alias, PullRequest.author_id == author_alias.id)
        .where(
            PullRequest.repo_id == repo_id,
            PullRequest.state == "open",
            PullRequest.updated_at < threshold,
        )
        .order_by(PullRequest.updated_at.asc())
    )

    return [
        StalePR(
            number=pr.number,
            title=pr.title,
            author=author_login,
            updated_at=ensure_utc(pr.updated_at),
            days_stale=(now - ensure_utc(pr.updated_at)).days,
        )
        for pr, author_login in db.execute(query).all()
    ]
