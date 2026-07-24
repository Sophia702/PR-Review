# PR-Review

PR/Code Review Analytics Dashboard — pulls PR and review data from the GitHub API for a repo (or org) and surfaces metrics that help a team understand its own review process: time-to-first-review, time-to-merge, review load distribution across teammates, stale PRs, etc.

This is genuinely useful internal-tooling territory — companies build exactly this kind of thing internally (Google, GitHub itself, LinearB, etc. all have commercial versions).

## Status

**Week 1 (ingestion) — done.** FastAPI service, SQLAlchemy models, GraphQL-based GitHub client, incremental sync via a stored cursor, sync tests against mocked GitHub responses.

**Week 2 (metrics layer) — done.** SQL-based metrics (time-to-first-review, time-to-merge, review load, stale PRs), wired into `/metrics/{owner}/{repo}/...` endpoints, tested against fixture data covering bot accounts, draft PRs, zero-review PRs, and PRs closed without merging.

**Validated against the live GitHub API** — synced `encode/httpx` end-to-end (41 PRs, real reviews, `dependabot` correctly flagged as a bot) and confirmed all four `/metrics` endpoints return sane numbers against real data.

**Week 2 (dashboard) — done.** React + TypeScript + Vite + Recharts dashboard in `frontend/`: repo picker with an inline sync/re-sync action, date-range and author filters, stat tiles for time-to-first-review and time-to-merge, a review-load bar chart, a weekly time-to-merge trend line, and a stale-PR table. Verified in an actual headless-Chromium run against the live-synced `encode/httpx` data — no console errors, real numbers rendered.

**CI — done.** `.github/workflows/ci.yml` runs the pytest suite (fresh venv) and the frontend typecheck+build (`tsc --noEmit && vite build`, fresh `npm ci`) on push/PR to `main`. Both verified locally exactly as CI would run them before committing the workflow.

**Deployment — config written, not yet live.** Fly.io (backend + frontend) + Neon (Postgres). See [DEPLOY.md](DEPLOY.md) — needs your Fly/Neon accounts to actually go live.

See [Suggested build order](#suggested-build-order-23-weeks) below for what's next.

## Core idea

Pull PR and review data from the GitHub API for a repo (or org) and surface metrics that help a team understand its own review process — time-to-first-review, time-to-merge, review load distribution across teammates, stale PRs, etc. This is genuinely useful internal-tooling territory — companies build exactly this kind of thing internally (Google, GitHub itself, LinearB, etc. all have commercial versions).

## Scope breakdown

### 1. Data ingestion (backend)

- FastAPI service authenticating via GitHub OAuth (or a personal access token to start, simpler)
- Pull PRs, reviews, comments, commits via GitHub's REST or GraphQL API for a given repo
- Store normalized data in PostgreSQL: `pull_requests`, `reviews`, `review_comments`, `users`, `repos`
- Background job (Celery, or just APScheduler if you want to keep it simpler) to periodically sync new data rather than re-fetching everything each time — this is a good engineering decision to point to ("incremental sync using GitHub's `updated_at` cursor rather than full re-pull")

**Built:** GraphQL (not REST) via `search(query: "repo:owner/name is:pr updated:>=...")`, since the plain `repository.pullRequests` connection has no `updated_at` filter. A `sync_state` table tracks the max `updatedAt` cursor per repo so reruns only pull what changed, falling back to a `BACKFILL_DAYS` window on first sync. Bots are flagged at ingestion time (`User.is_bot`, from GraphQL's `__typename`) rather than filtered ad hoc later. APScheduler over Celery — no broker needed for a single-service deploy. (Scheduled job itself not wired up yet — sync currently runs via the API or the CLI script.)

### 2. Metrics/analytics layer

This is where the actual engineering thinking lives — pick a handful of well-defined, non-trivial metrics:

- **Time-to-first-review**: PR opened → first review submitted
- **Time-to-merge**: PR opened → merged
- **Review load**: reviews given per person, to spot bottlenecks (one person reviewing everything)
- **Stale PR detection**: open >N days with no activity
- **Review reciprocity** (fun one, stretch goal): does person A review person B's PRs but not vice versa — could surface team dynamics

Compute these as SQL aggregations or pandas — either is defensible, pandas is faster to prototype with.

**Built:** all five as SQL aggregations (SQLAlchemy Core `select`/`func`, not pandas) in `backend/app/metrics.py`, so they run live against `/metrics` without loading full tables into memory. Review reciprocity has a `min_interactions` floor (default 2) so single-review noise doesn't get reported as a "pattern" — validated against `encode/httpx`, which surfaced a real one-directional pair.

### 3. Frontend/dashboard

- React + a charting library (Recharts) — bar charts for review load, line chart for time-to-merge trend over weeks, a table of stale PRs
- Filterable by repo, by date range, by author

**Built:** `frontend/` — Vite + React + TypeScript + Recharts. Repo picker (with an inline sync/re-sync button so you don't need the API directly), since/until/author filters, a stale-days threshold control, plus a review-reciprocity table flagging one-directional review pairs. Time-to-merge trend is bucketed into weekly medians client-side from the `time-to-merge` endpoint's per-PR items, rather than a dedicated backend aggregation. Chart colors and mark specs (bar thickness, line width, tooltip styling, stale/reciprocity badges) follow a validated categorical/sequential palette rather than library defaults.

### 4. Testing + CI

- pytest for the ingestion logic (mock GitHub API responses) and the metrics calculations — this is the part with real edge cases (PRs with zero reviews, PRs reviewed then reopened, bot accounts skewing review-load stats)
- GitHub Actions running tests on push

**Built:** pytest suite (`tests/test_sync.py`, `tests/test_metrics.py`) covering pagination, bot-account flagging, idempotent re-sync, zero-review PRs, draft-PR exclusion, and merged-vs-closed-without-merge PRs. `.github/workflows/ci.yml` runs the suite plus the frontend build on push/PR.

### 5. Deployment

- Deploy against a real public repo (maybe your own repo, or a popular open-source repo) so the dashboard has real data and a live demo link

**Config written, not yet live.** Dockerfiles + `fly.toml` for both apps (backend on Fly, frontend static build served via nginx on Fly), targeting Neon for managed Postgres. See [DEPLOY.md](DEPLOY.md) for the full walkthrough — the login/account-creation steps need your Fly and Neon accounts, so those are still open. Already synced against `encode/httpx` for local validation (few hundred PRs, not thousands — a large OSS repo would hit rate limits or take a long time on first backfill).

## Suggested build order (2–3 weeks)

- **Week 1**: GitHub API ingestion + DB schema + basic sync script (get this working end-to-end before touching UI) — *done*
- **Week 2**: Metrics layer + tests for it, then basic React dashboard hitting a `/metrics` endpoint — *done*
- **Week 3**: Polish — incremental sync, stale-PR detection, deploy, write README with a screenshot — *incremental sync, stale-PR detection, and CI already done as part of Weeks 1–2; deploy still open*

## Resume-bullet potential (draft)

- Built a PR analytics dashboard (FastAPI, PostgreSQL, React) ingesting GitHub API data via incremental sync, surfacing review-load and time-to-merge metrics across a repo's contributors
- Designed metrics (time-to-first-review, stale-PR detection, review-load distribution) as SQL aggregations over a normalized PR/review schema, validated against [X] real repos
- Wrote a pytest suite mocking GitHub API responses to test ingestion and metric edge cases (bot accounts, reopened PRs, zero-review merges)

## Running it

```bash
# from repo root
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt

cp backend/.env.example backend/.env   # fill in GITHUB_TOKEN, DATABASE_URL

# tests (use in-memory SQLite, no GitHub token or Postgres needed)
.venv/bin/python -m pytest

# run the API (needs Postgres reachable at DATABASE_URL)
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --reload

# one-off incremental sync from the CLI, instead of via the API
PYTHONPATH=backend .venv/bin/python backend/scripts/sync_repo.py <owner> <repo>
```

Endpoints once the app is running:

- `GET /repos` — repos synced so far
- `POST /sync/{owner}/{repo}` — trigger an incremental sync
- `GET /metrics/{owner}/{repo}/time-to-first-review?since=&until=&author=`
- `GET /metrics/{owner}/{repo}/time-to-merge?since=&until=&author=`
- `GET /metrics/{owner}/{repo}/review-load?since=&until=`
- `GET /metrics/{owner}/{repo}/stale-prs?stale_days=14`
- `GET /metrics/{owner}/{repo}/review-reciprocity?min_interactions=2`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL defaults to http://localhost:8000

npm run dev             # http://localhost:5173, needs the backend running
npm run build            # type-checks (tsc --noEmit) then produces dist/
```

See [DEPLOY.md](DEPLOY.md) for deploying both to Fly.io with Neon Postgres.

The backend needs `CORS_ALLOW_ORIGINS` to include the dev server's origin — it already defaults to `["http://localhost:5173"]` in `backend/app/config.py`.
