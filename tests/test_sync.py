from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.github_client import GitHubClient
from app.models import PullRequest, Review, SyncState, User
from app.sync import sync_repo

GRAPHQL_URL = "https://api.github.com/graphql"


def _iso(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pr_node(number, github_id, updated_at, author_login="alice", author_type="User", reviews=None, is_draft=False):
    return {
        "id": github_id,
        "number": number,
        "title": f"PR #{number}",
        "state": "OPEN",
        "isDraft": is_draft,
        "createdAt": _iso(3),
        "updatedAt": updated_at,
        "mergedAt": None,
        "closedAt": None,
        "author": {"login": author_login, "__typename": author_type},
        "reviews": {"nodes": reviews or []},
        "reviewThreads": {"nodes": []},
    }


def _search_response(nodes, has_next_page=False, end_cursor=None):
    return httpx.Response(
        200,
        json={
            "data": {
                "search": {
                    "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                    "nodes": nodes,
                }
            }
        },
    )


@respx.mock
def test_sync_repo_creates_prs_and_reviews(db_session):
    pr_updated_at = _iso(2)
    respx.post(GRAPHQL_URL).mock(
        return_value=_search_response(
            [
                _pr_node(
                    1,
                    "PR_1",
                    pr_updated_at,
                    reviews=[
                        {
                            "id": "REV_1",
                            "state": "APPROVED",
                            "submittedAt": _iso(1),
                            "author": {"login": "bob", "__typename": "User"},
                        }
                    ],
                )
            ]
        )
    )

    client = GitHubClient(token="fake-token")
    synced = sync_repo(db_session, "acme", "widgets", client=client)

    assert synced == 1
    pr = db_session.query(PullRequest).filter_by(github_id="PR_1").one()
    assert pr.number == 1
    assert pr.author.login == "alice"

    review = db_session.query(Review).filter_by(github_id="REV_1").one()
    assert review.state == "APPROVED"
    assert review.reviewer.login == "bob"

    sync_state = db_session.query(SyncState).filter_by(repo_id=pr.repo_id).one()
    expected = datetime.fromisoformat(pr_updated_at.replace("Z", "+00:00"))
    assert sync_state.last_synced_at.replace(tzinfo=timezone.utc) == expected


@respx.mock
def test_sync_repo_paginates_through_all_results(db_session):
    respx.post(GRAPHQL_URL).mock(
        side_effect=[
            _search_response([_pr_node(1, "PR_1", _iso(2))], has_next_page=True, end_cursor="CURSOR_1"),
            _search_response([_pr_node(2, "PR_2", _iso(1))]),
        ]
    )

    client = GitHubClient(token="fake-token")
    synced = sync_repo(db_session, "acme", "widgets", client=client)

    assert synced == 2
    numbers = {pr.number for pr in db_session.query(PullRequest).all()}
    assert numbers == {1, 2}


@respx.mock
def test_sync_repo_flags_bot_authors(db_session):
    respx.post(GRAPHQL_URL).mock(
        return_value=_search_response(
            [_pr_node(1, "PR_1", _iso(1), author_login="dependabot[bot]", author_type="Bot")]
        )
    )

    client = GitHubClient(token="fake-token")
    sync_repo(db_session, "acme", "widgets", client=client)

    user = db_session.query(User).filter_by(login="dependabot[bot]").one()
    assert user.is_bot is True


@respx.mock
def test_sync_repo_is_idempotent_on_rerun(db_session):
    respx.post(GRAPHQL_URL).mock(return_value=_search_response([_pr_node(1, "PR_1", _iso(1))]))

    client = GitHubClient(token="fake-token")
    sync_repo(db_session, "acme", "widgets", client=client)
    sync_repo(db_session, "acme", "widgets", client=client)

    assert db_session.query(PullRequest).count() == 1
    assert db_session.query(User).count() == 1


@respx.mock
def test_sync_repo_handles_pr_with_zero_reviews(db_session):
    respx.post(GRAPHQL_URL).mock(return_value=_search_response([_pr_node(1, "PR_1", _iso(1), reviews=[])]))

    client = GitHubClient(token="fake-token")
    synced = sync_repo(db_session, "acme", "widgets", client=client)

    assert synced == 1
    assert db_session.query(Review).count() == 0
