from __future__ import annotations

import httpx

from app.config import get_settings

# GitHub's `repository.pullRequests` connection has no `updated_at` filter, so
# incremental sync goes through `search` instead, which supports the
# `updated:>=` qualifier. This is what lets sync_repo() ask for "PRs touched
# since my last cursor" instead of re-pulling the whole repo every run.
SEARCH_QUERY = """
query($searchQuery: String!, $after: String) {
  search(query: $searchQuery, type: ISSUE, first: 25, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on PullRequest {
        id
        number
        title
        state
        isDraft
        createdAt
        updatedAt
        mergedAt
        closedAt
        author {
          login
          __typename
        }
        reviews(first: 50) {
          nodes {
            id
            state
            submittedAt
            author {
              login
              __typename
            }
          }
        }
        reviewThreads(first: 50) {
          nodes {
            comments(first: 20) {
              nodes {
                id
                createdAt
                author {
                  login
                  __typename
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


class GitHubGraphQLError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str | None = None, api_url: str | None = None):
        settings = get_settings()
        self._api_url = api_url or settings.github_graphql_url
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token or settings.github_token}"},
            timeout=30.0,
        )

    def search_pull_requests(self, search_query: str, after: str | None = None) -> dict:
        response = self._client.post(
            self._api_url,
            json={
                "query": SEARCH_QUERY,
                "variables": {"searchQuery": search_query, "after": after},
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            raise GitHubGraphQLError(payload["errors"])
        return payload["data"]["search"]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
