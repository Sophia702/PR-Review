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
  SYNC_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  SESSION_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  SESSION_ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  SESSION_COOKIE_SECURE=true \
  FRONTEND_URL="https://pr-review-dashboard.fly.dev" \
  BACKEND_PUBLIC_URL="https://pr-review-api.fly.dev" \
  GITHUB_OAUTH_CLIENT_ID="<from a GitHub OAuth App, see below>" \
  GITHUB_OAUTH_CLIENT_SECRET="<from the same OAuth App>" \
  --app pr-review-api

fly deploy --app pr-review-api
```

`CORS_ALLOW_ORIGINS` should be the frontend's eventual Fly URL (step 4) — comma-separate if you need more than one origin. `SYNC_API_KEY` gates `POST /sync` alongside GitHub OAuth (either satisfies it) — without the key configured and nobody logged in, that endpoint rejects every request (fails closed), since it's the one action that costs real GitHub API quota and Neon storage on every call. No local Docker daemon is required; `fly deploy` builds remotely on Fly's infrastructure if Docker isn't running locally.

For the OAuth credentials: create an OAuth App at [github.com/settings/developers](https://github.com/settings/developers) → New OAuth App, with:
- Homepage URL: `https://pr-review-dashboard.fly.dev`
- Authorization callback URL: `https://pr-review-api.fly.dev/auth/github/callback`

then generate a Client Secret and use both values above.

Once deployed, create the tables and do the first sync (needs the key from the `fly secrets set` above):

```bash
curl -X POST -H "X-API-Key: <your SYNC_API_KEY>" https://pr-review-api.fly.dev/sync/encode/httpx
```

After that, tracked repos re-sync automatically every `SYNC_INTERVAL_MINUTES` (default 30) — no need to keep calling this manually. The dashboard's own "Sync"/"Re-sync" button also asks for this key at runtime (never baked into the frontend build, since that's public and static).

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

## Status

Live: https://pr-review-dashboard.fly.dev / https://pr-review-api.fly.dev, backed by Neon, synced against `encode/httpx`. Deployed by walking through exactly the steps above — `fly auth login` needs a real interactive terminal (it fails in headless/agent environments asking for `FLY_API_TOKEN`), so that step has to run in your own terminal; everything after (`fly apps create`, `fly secrets set`, `fly deploy`) works fine non-interactively once you're logged in.

`POST /sync` was briefly live without the `SYNC_API_KEY` guard (any request would trigger a sync against arbitrary GitHub repos on this instance's token/DB). Fixed and redeployed — verified against the live URL that unauthenticated and wrong-key requests both 401, the correct key still works, and `/health`/`/repos`/`/metrics/*` stayed public throughout.

GitHub OAuth login and commit-level ingestion added and deployed — verified: the login redirect carries the real `client_id` and correct `redirect_uri`/`return_to`, `/auth/me` and `/sync` (via API key) both work against the live API, and the `commits` table has real rows in production Neon. **The actual "click Login, authorize on github.com" step needs a real GitHub account** — that one has to be clicked through by a human once, since it can't be driven programmatically.

## Notes

- Verified the Neon connection and every metrics endpoint against real Postgres (not just SQLite) before deploying, then re-verified the live public URL with a headless-Chromium screenshot after.
- Both apps came up with 2 machines each — that's Fly's default HA behavior on first deploy (pass `--ha=false` to avoid it), independent of `min_machines_running`. `auto_stop_machines = true` / `min_machines_running = 0` still means they scale to zero and cold-start (a few seconds) when idle.
- Re-running a sync (`POST /sync/{owner}/{repo}`) is safe and incremental — it won't re-pull history it already has.
