from datetime import datetime, timedelta, timezone

import pytest

from app import metrics
from app.models import PullRequest, Repo, Review, User

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _repo(db):
    repo = Repo(owner="acme", name="widgets")
    db.add(repo)
    db.flush()
    return repo


def _user(db, login, is_bot=False):
    user = db.query(User).filter_by(login=login).one_or_none()
    if user is None:
        user = User(login=login, is_bot=is_bot)
        db.add(user)
        db.flush()
    return user


def _pr(
    db,
    repo,
    number,
    author,
    *,
    created_at,
    updated_at=None,
    merged_at=None,
    closed_at=None,
    state="open",
    is_draft=False,
):
    pr = PullRequest(
        github_id=f"PR_{number}",
        repo_id=repo.id,
        number=number,
        title=f"PR #{number}",
        author_id=author.id if author else None,
        state=state,
        is_draft=is_draft,
        created_at=created_at,
        updated_at=updated_at or created_at,
        merged_at=merged_at,
        closed_at=closed_at,
    )
    db.add(pr)
    db.flush()
    return pr


def _review(db, pr, reviewer, *, submitted_at, state="APPROVED"):
    review = Review(
        github_id=f"REV_{pr.number}_{reviewer.login}_{submitted_at.isoformat()}",
        pull_request_id=pr.id,
        reviewer_id=reviewer.id,
        state=state,
        submitted_at=submitted_at,
    )
    db.add(review)
    db.flush()
    return review


def test_time_to_first_review_uses_earliest_non_bot_review(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    ci_bot = _user(db_session, "ci-bot", is_bot=True)

    pr = _pr(db_session, repo, 1, alice, created_at=NOW)
    _review(db_session, pr, ci_bot, submitted_at=NOW + timedelta(minutes=1))
    _review(db_session, pr, bob, submitted_at=NOW + timedelta(hours=5))

    summary = metrics.time_to_first_review(db_session, repo.id)

    assert summary.count == 1
    assert summary.items[0].hours == pytest.approx(5.0)


def test_time_to_first_review_excludes_prs_with_zero_reviews(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    _pr(db_session, repo, 1, alice, created_at=NOW)

    summary = metrics.time_to_first_review(db_session, repo.id)

    assert summary.count == 0
    assert summary.items == []
    assert summary.avg_hours is None


def test_time_to_first_review_excludes_draft_prs(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    pr = _pr(db_session, repo, 1, alice, created_at=NOW, is_draft=True)
    _review(db_session, pr, bob, submitted_at=NOW + timedelta(hours=2))

    summary = metrics.time_to_first_review(db_session, repo.id)

    assert summary.count == 0


def test_time_to_first_review_filters_by_author(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    carol = _user(db_session, "carol")
    bob = _user(db_session, "bob")
    alice_pr = _pr(db_session, repo, 1, alice, created_at=NOW)
    carol_pr = _pr(db_session, repo, 2, carol, created_at=NOW)
    _review(db_session, alice_pr, bob, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, carol_pr, bob, submitted_at=NOW + timedelta(hours=1))

    summary = metrics.time_to_first_review(db_session, repo.id, author="alice")

    assert summary.count == 1
    assert summary.items[0].number == 1


def test_time_to_merge_only_counts_merged_prs(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    _pr(db_session, repo, 1, alice, created_at=NOW, merged_at=NOW + timedelta(days=2), state="merged")
    _pr(db_session, repo, 2, alice, created_at=NOW, closed_at=NOW + timedelta(days=1), state="closed")

    summary = metrics.time_to_merge(db_session, repo.id)

    assert summary.count == 1
    assert summary.items[0].number == 1
    assert summary.items[0].hours == pytest.approx(48.0)


def test_review_load_excludes_bots_and_counts_per_reviewer(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    ci_bot = _user(db_session, "ci-bot", is_bot=True)

    pr1 = _pr(db_session, repo, 1, alice, created_at=NOW)
    pr2 = _pr(db_session, repo, 2, alice, created_at=NOW)
    _review(db_session, pr1, bob, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, pr2, bob, submitted_at=NOW + timedelta(hours=2))
    _review(db_session, pr1, ci_bot, submitted_at=NOW + timedelta(minutes=1))

    load = metrics.review_load(db_session, repo.id)

    assert load == [metrics.ReviewerLoad(reviewer="bob", review_count=2)]


def test_review_load_reflects_reopened_pr_via_latest_snapshot(db_session):
    # PullRequest rows are upserted on github_id, so a reopened PR's state
    # reflects the latest sync rather than a full event history - reviews
    # given on it while it was previously open/closed still count once.
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    pr = _pr(db_session, repo, 1, alice, created_at=NOW, state="open")
    _review(db_session, pr, bob, submitted_at=NOW + timedelta(hours=1))

    load = metrics.review_load(db_session, repo.id)

    assert load == [metrics.ReviewerLoad(reviewer="bob", review_count=1)]


def test_stale_prs_only_returns_open_prs_past_threshold(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    _pr(
        db_session,
        repo,
        1,
        alice,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW - timedelta(days=20),
        state="open",
    )
    _pr(
        db_session,
        repo,
        2,
        alice,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW - timedelta(days=1),
        state="open",
    )
    _pr(
        db_session,
        repo,
        3,
        alice,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW - timedelta(days=25),
        state="merged",
        merged_at=NOW - timedelta(days=25),
    )

    stale = metrics.stale_prs(db_session, repo.id, stale_days=14, now=NOW)

    assert [s.number for s in stale] == [1]
    assert stale[0].days_stale == 20


def test_review_reciprocity_detects_one_directional_pair(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")

    # bob reviews alice's PRs twice; alice never reviews bob's.
    alice_pr1 = _pr(db_session, repo, 1, alice, created_at=NOW)
    alice_pr2 = _pr(db_session, repo, 2, alice, created_at=NOW)
    _review(db_session, alice_pr1, bob, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, alice_pr2, bob, submitted_at=NOW + timedelta(hours=2))

    pairs = metrics.review_reciprocity(db_session, repo.id, min_interactions=2)

    assert len(pairs) == 1
    pair = pairs[0]
    assert {pair.person_a, pair.person_b} == {"alice", "bob"}
    assert pair.one_directional is True
    counts = {pair.person_a: pair.a_reviews_b, pair.person_b: pair.b_reviews_a}
    assert counts["bob"] == 2  # bob -> alice
    assert counts["alice"] == 0  # alice -> bob


def test_review_reciprocity_symmetric_pair_is_not_one_directional(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")

    alice_pr = _pr(db_session, repo, 1, alice, created_at=NOW)
    bob_pr = _pr(db_session, repo, 2, bob, created_at=NOW)
    _review(db_session, alice_pr, bob, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, bob_pr, alice, submitted_at=NOW + timedelta(hours=1))

    pairs = metrics.review_reciprocity(db_session, repo.id, min_interactions=2)

    assert len(pairs) == 1
    assert pairs[0].one_directional is False


def test_review_reciprocity_excludes_bots_and_self_reviews(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    ci_bot = _user(db_session, "ci-bot", is_bot=True)

    pr = _pr(db_session, repo, 1, alice, created_at=NOW)
    _review(db_session, pr, ci_bot, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, pr, alice, submitted_at=NOW + timedelta(hours=2))  # self-review edge case

    pairs = metrics.review_reciprocity(db_session, repo.id, min_interactions=1)

    assert pairs == []


def test_review_reciprocity_filters_pairs_below_min_interactions(db_session):
    repo = _repo(db_session)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    carol = _user(db_session, "carol")

    # alice/bob: only 1 interaction total -> filtered out at default threshold of 2
    alice_pr = _pr(db_session, repo, 1, alice, created_at=NOW)
    _review(db_session, alice_pr, bob, submitted_at=NOW + timedelta(hours=1))

    # alice/carol: 2 interactions -> kept
    alice_pr2 = _pr(db_session, repo, 2, alice, created_at=NOW)
    carol_pr = _pr(db_session, repo, 3, carol, created_at=NOW)
    _review(db_session, alice_pr2, carol, submitted_at=NOW + timedelta(hours=1))
    _review(db_session, carol_pr, alice, submitted_at=NOW + timedelta(hours=1))

    pairs = metrics.review_reciprocity(db_session, repo.id, min_interactions=2)

    assert len(pairs) == 1
    assert {pairs[0].person_a, pairs[0].person_b} == {"alice", "carol"}
