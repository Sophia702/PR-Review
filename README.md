# PR Review Analytics

A dashboard that turns a GitHub repo's pull request history into the metrics an engineering team actually wants to know: how long reviews take, who's carrying the review load, which PRs have gone stale, and whether review relationships are lopsided.

**Live app:** [pr-review-dashboard.fly.dev](https://pr-review-dashboard.fly.dev) · **API:** [pr-review-api.fly.dev](https://pr-review-api.fly.dev)

*(Fly apps sleep when idle — the first load may take a few seconds to wake up.)*

![Dashboard screenshot](docs/screenshot.png)

## What it does

- **Time-to-first-review** and **time-to-merge** — median and average, with per-PR detail
- **Review load** — reviews given per person, to spot who's reviewing everything and who never gets asked
- **Stale PR detection** — open PRs with no activity past a configurable threshold
- **Review reciprocity** — flags one-directional review relationships (A reviews B repeatedly, B never reciprocates)
- Filterable by date range and author; syncs any repo on demand, then keeps it fresh automatically
- **Log in with GitHub** to sync under your own account instead of the shared API key — your sync draws from your own rate limit, not a shared one

## Architecture notes

A few decisions worth calling out:

- **Incremental sync via GraphQL `search`, not the plain PR connection.** GitHub's `repository.pullRequests` has no `updated_at` filter, so a real incremental sync has to go through `search(query: "repo:owner/name is:pr updated:>=...")` instead. A stored cursor per repo means re-syncs only pull what changed rather than re-fetching history — a fresh repo does one backfill, then costs almost nothing on every run after.
- **Metrics are SQL, not pandas.** Time-to-first-review, time-to-merge, review load, stale-PR detection, and reciprocity are all computed as SQL aggregations (window functions, correlated subqueries) directly against Postgres, so they run live on request instead of needing a precomputed cache or an in-memory DataFrame.
- **Bot accounts and draft PRs are handled at the source.** Bots are flagged at ingestion time (from GitHub's `__typename`) so they don't skew review-load or reciprocity numbers downstream. Draft PRs are excluded from time-to-first-review, since GitHub's API has no `readyForReviewAt` field to correct the clock for them.
- **The write path is the only thing gated.** `POST /sync` is the one endpoint that costs real GitHub API quota and database storage per call, so it's the only one behind auth (API key or a logged-in session, either satisfies it — constant-time comparison for the key, fails closed if neither is present). Everything read-only — the metrics themselves — stays public. The frontend asks for the key at runtime rather than baking it into the build, since a static site's JS bundle is public regardless of what "looks" hidden in it.
- **A background scheduler, not a cron job someone has to remember.** Every tracked repo re-syncs on an interval automatically, each in its own transaction so one repo's failure can't affect the others in the same run.
- **OAuth sessions live in a signed, encrypted cookie — not a database table.** Both Fly apps run 2 machines behind a load balancer; a server-side session store would need every machine to agree on state, while a signed cookie (Starlette `SessionMiddleware`) works identically regardless of which machine handles a request, no shared state required. The GitHub token inside it is additionally `Fernet`-encrypted, not just signed — the cookie is tamper-evident either way, but that stops the raw token from being readable by anyone who obtains it. When a logged-in user triggers a sync, their own token is used for that sync's GitHub calls instead of the shared one — real delegation, not just a nicer login screen.
- **Commit ingestion is need-driven, not exhaustive.** PRs, reviews, comments, and now commits are all normalized into Postgres, but nothing pulls more than the metrics actually require — commits, for instance, are stored but don't yet back a metric of their own.

## Stack

| | |
|---|---|
| Backend | FastAPI · SQLAlchemy · PostgreSQL ([Neon](https://neon.tech)) · APScheduler |
| Frontend | React · TypeScript · Vite · Recharts |
| Ingestion | GitHub GraphQL API via `httpx` |
| Auth | GitHub OAuth · signed/encrypted session cookies (`itsdangerous`, `cryptography`) |
| Testing | pytest, with `respx` for mocked GitHub responses |
| Deploy | Docker on [Fly.io](https://fly.io), GitHub Actions CI |

## Testing

The interesting edge cases for a project like this aren't the happy path — they're PRs with zero reviews, bot accounts inflating review-load numbers, draft PRs, PRs closed without merging, and reopened PRs. All of those are covered in `tests/`, exercised against mocked GraphQL fixtures rather than the live API, so the suite runs in well under a second with no network or database dependency.

```bash
pytest   # in-memory SQLite, nothing external required
```

## Running locally

**Backend**
```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # GITHUB_TOKEN, DATABASE_URL, SYNC_API_KEY, SESSION_SECRET_KEY, SESSION_ENCRYPTION_KEY
uvicorn app.main:app --reload
```

GitHub OAuth login itself needs real HTTPS to work (the session cookie is `SameSite=None; Secure`, since the frontend and backend are different origins — browsers only honor that over HTTPS), so it can only be exercised end-to-end against the deployed instance. Locally, sync via `SYNC_API_KEY` instead.

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env
npm run dev   # http://localhost:5173
```

## API

| Endpoint | Notes |
|---|---|
| `GET /repos` | Repos synced so far |
| `POST /sync/{owner}/{repo}` | Trigger an incremental sync — requires `X-API-Key` |
| `GET /metrics/{owner}/{repo}/time-to-first-review` | `?since=&until=&author=` |
| `GET /metrics/{owner}/{repo}/time-to-merge` | `?since=&until=&author=` |
| `GET /metrics/{owner}/{repo}/review-load` | `?since=&until=` |
| `GET /metrics/{owner}/{repo}/stale-prs` | `?stale_days=14` |
| `GET /metrics/{owner}/{repo}/review-reciprocity` | `?min_interactions=2` |
| `GET /auth/github/login` | Starts the OAuth handshake — `?return_to=` |
| `GET /auth/github/callback` | OAuth redirect target, not called directly |
| `GET /auth/me` | `{"github_login": "..." \| null}` |
| `POST /auth/logout` | Clears the session |

## Deployment

Two Fly.io apps (backend + a static frontend build behind nginx) and a Neon Postgres instance. Full walkthrough in [DEPLOY.md](DEPLOY.md).

## Possible extensions

- **Rate-limit backoff** on the GitHub client, for syncing repos large enough to hit it
- **A metric built on commit data** — e.g. time from first commit to PR open, or commit count as a churn signal — now that commits are actually ingested
