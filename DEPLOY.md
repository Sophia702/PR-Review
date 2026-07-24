# Deploying (Fly.io + Neon)

Two Fly apps — `backend/` (FastAPI, Dockerfile) and `frontend/` (static build served via nginx, Dockerfile) — plus a Neon Postgres database. `flyctl` is already installed locally; everything below needs your Fly and Neon accounts, so the login/account-creation steps are yours to run.

## 1. Neon (Postgres)

1. Create a project at [neon.tech](https://neon.tech) (free tier is enough for a demo repo).
2. Copy the connection string from the Neon dashboard. It looks like:
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require
   ```
3. Change the scheme to `postgresql+psycopg://` (SQLAlchemy dialect for psycopg3) — keep everything else, including `?sslmode=require`:
   ```
   postgresql+psycopg://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require
   ```
   That's your `DATABASE_URL`.

## 2. Fly login

```bash
fly auth login   # opens a browser — this has to be you
```

## 3. Backend

App names are globally unique on Fly — `backend/fly.toml` ships with `app = "pr-review-api"` as a placeholder; change it (in `fly.toml`) if that's taken.

```bash
cd backend
fly apps create pr-review-api   # or whatever you renamed it to in fly.toml

fly secrets set \
  DATABASE_URL="postgresql+psycopg://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require" \
  GITHUB_TOKEN="ghp_..." \
  CORS_ALLOW_ORIGINS="https://pr-review-dashboard.fly.dev" \
  --app pr-review-api

fly deploy --app pr-review-api
```

`CORS_ALLOW_ORIGINS` should be the frontend's eventual Fly URL (step 4) — comma-separate if you need more than one origin. No local Docker daemon is required; `fly deploy` builds remotely on Fly's infrastructure if Docker isn't running locally.

Once deployed, create the tables and do the first sync:

```bash
curl -X POST https://pr-review-api.fly.dev/sync/encode/httpx
```

(SQLAlchemy's `Base.metadata.create_all` runs on app startup, so the schema is already there by the time this call lands.)

## 4. Frontend

The frontend needs the backend's URL baked in **at build time** (Vite inlines `VITE_*` vars into the JS bundle, not read at runtime) — pass it as a Docker build arg:

```bash
cd frontend
fly apps create pr-review-dashboard   # or your renamed app

fly deploy --app pr-review-dashboard \
  --build-arg VITE_API_BASE_URL=https://pr-review-api.fly.dev
```

## 5. Verify

Open `https://pr-review-dashboard.fly.dev` — the repo picker should show `encode/httpx` (or whatever you synced) with real metrics. If it's blank, check:

- `fly logs --app pr-review-api` for backend errors (most likely: `DATABASE_URL` scheme or Neon SSL)
- Browser devtools console for CORS errors (most likely: `CORS_ALLOW_ORIGINS` doesn't match the frontend's actual URL)

## Notes

- I wrote and reviewed these Dockerfiles/configs but couldn't build-test them end-to-end — there's no local Docker daemon and I don't have Fly/Neon credentials in this environment. The underlying `pip install`/`npm run build` commands they wrap were verified separately (see README status). Worth watching the first `fly deploy` output closely.
- `auto_stop_machines = true` / `min_machines_running = 0` in both `fly.toml`s means the app sleeps when idle and cold-starts on the next request (a few seconds) — fine for a demo, not for anything latency-sensitive.
- Re-running a sync (`POST /sync/{owner}/{repo}`) is safe and incremental — it won't re-pull history it already has.
