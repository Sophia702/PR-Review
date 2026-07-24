from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.github_client import GitHubClient
from app.models import Commit, PullRequest, Review, SyncState, User
from app.sync import sync_repo

GRAPHQL_URL = "https://api.github.com/graphql"


def _iso(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pr_node(
    number, github_id, updated_at, author_login="alice", author_type="User", reviews=None, is_draft=False, commits=None
):
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
        "commits": {"nodes": commits or []},
    }


def _commit_node(oid, message="fix stuff", committed_at=None, author_login="alice", author_type="User"):
    return {
        "commit": {
            "oid": oid,
            "message": message,
            "committedDate": committed_at or _iso(2.5),
            "author": {"user": {"login": author_login, "__typename": author_type} if author_login else None},
        }
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


@respx.mock
def test_sync_repo_ingests_commits(db_session):
    respx.post(GRAPHQL_URL).mock(
        return_value=_search_response(
            [
                _pr_node(
                    1,
                    "PR_1",
                    _iso(1),
                    commits=[
                        _commit_node("SHA_1", message="add feature", author_login="bob"),
                        _commit_node("SHA_2", message="fix typo", author_login="bob"),
                    ],
                )
            ]
        )
    )

    client = GitHubClient(token="fake-token")
    sync_repo(db_session, "acme", "widgets", client=client)

    commits = db_session.query(Commit).order_by(Commit.github_id).all()
    assert [c.github_id for c in commits] == ["SHA_1", "SHA_2"]
    assert commits[0].message == "add feature"
    assert commits[0].author.login == "bob"


@respx.mock
def test_sync_repo_handles_pr_with_zero_commits(db_session):
    respx.post(GRAPHQL_URL).mock(return_value=_search_response([_pr_node(1, "PR_1", _iso(1), commits=[])]))

    client = GitHubClient(token="fake-token")
    synced = sync_repo(db_session, "acme", "widgets", client=client)

    assert synced == 1
    assert db_session.query(Commit).count() == 0


@respx.mock
def test_sync_repo_commit_with_no_linked_github_user(db_session):
    respx.post(GRAPHQL_URL).mock(
        return_value=_search_response(
            [_pr_node(1, "PR_1", _iso(1), commits=[_commit_node("SHA_1", author_login=None)])]
        )
    )

    client = GitHubClient(token="fake-token")
    sync_repo(db_session, "acme", "widgets", client=client)

    commit = db_session.query(Commit).filter_by(github_id="SHA_1").one()
    assert commit.author_id is None


@respx.mock
def test_sync_repo_commits_idempotent_on_rerun(db_session):
    respx.post(GRAPHQL_URL).mock(
        return_value=_search_response([_pr_node(1, "PR_1", _iso(1), commits=[_commit_node("SHA_1")])])
    )

    client = GitHubClient(token="fake-token")
    sync_repo(db_session, "acme", "widgets", client=client)
    sync_repo(db_session, "acme", "widgets", client=client)

    assert db_session.query(Commit).count() == 1
