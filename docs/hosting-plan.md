# Hosting DCMS for a friend's free-tier test (Vercel + Supabase + Render)

## Context

The goal is to let an advocate friend try the app over the internet, using
only free hosting tiers. The question was whether Vercel + Supabase alone
covers it.

They don't, for one specific reason: `docs/adr/0004-server-side-browser-with-proxied-captcha.md`
deliberately puts a single, always-running Playwright `Browser` process and an
in-memory `SessionRegistry` (`backend/app/dcms/browser.py:15-16`,
`backend/app/dcms/session.py:79`) behind the ingest flow, so a human can solve
the CAPTCHA over several requests spread across real time. That is the opposite
of a Vercel serverless function — no shared memory across invocations, and a
10s execution limit on the free tier. Vercel can't run this backend at any
price tier's "serverless functions" product; it needs a normal persistent
process somewhere.

The rest of the app is unusually hosting-friendly already: the frontend is a
clean Next.js app with no server-side Playwright dependency, session auth is a
signed cookie (not server memory) via Starlette's `SessionMiddleware`
(`backend/app/main.py:35-41`), and the DB layer uses only standard Postgres
features (`UUID`, `JSONB`, one partial unique index) that Supabase supports
natively.

Decisions made: backend runs on **Render's free Web Service** tier (accepting
the 15-minute idle spin-down and the resulting cold start — Chromium has to
relaunch — on the first request after idle), and **real case data is fine** to
use for this test, so no seed/dummy-data step is required beyond the usual
advocate accounts.

## Target architecture

| Piece | Where | Why |
|---|---|---|
| Frontend (Next.js 16) | Vercel free tier | As-is; no code changes needed |
| Backend (FastAPI + Playwright) | Render free Web Service (Docker) | Only free-tier option that gives a real persistent process for the browser/session registry |
| Database | Supabase free tier Postgres | Standard Postgres feature set, asyncpg-compatible |

The existing "browser sees one origin" design (`frontend/next.config.ts:9-11`,
rewriting `/api/*` to `BACKEND_URL`) is exactly what makes a split
Vercel/Render deployment work without touching CORS or cookie `SameSite`
settings — the rewrite is a server-to-server proxy, so the browser only ever
talks to the Vercel domain. Keep it; just point `BACKEND_URL` at the Render
service.

## Changes needed

1. **New `backend/Dockerfile`** (none exists today). Base on a slim Python
   image, install `uv`, `uv sync --frozen --no-dev`, then
   `uv run playwright install --with-deps chromium` (installing at build time
   rather than picking a pre-built Playwright image keeps the browser version
   in lockstep with whatever `playwright>=1.62.0` resolves to in `uv.lock`).
   The `CMD` must bind to Render's `$PORT`, not the hardcoded `8000` used
   locally:
   `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.

2. **New `backend/.dockerignore`** — exclude `.venv`, `tests/`,
   `credentials.txt`, `.env`.

3. **`backend/app/main.py:44`** — `allow_origins=["http://localhost:3000"]` is
   hardcoded. Add the Vercel production URL alongside it. (Low-stakes because
   the browser never calls Render directly through the rewrite proxy, but
   cheap to make correct, and it matters if you or the friend ever hit the
   Render URL directly, e.g. to check `/api/health`.)

4. **No frontend code changes.** `frontend/next.config.ts` already reads
   `BACKEND_URL` from the environment — set it in Vercel's project settings.

5. **Environment variables to set** (dashboard-only, never commit):
   - Render: `DATABASE_URL` (Supabase connection string, keep the
     `postgresql+asyncpg://` prefix), `SESSION_SECRET` (generate with
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`, same as
     the existing `.env.example` instructions), `DEBUG=false` (this flips
     `https_only=True` on the session cookie in `main.py:40` — required since
     both Render and Vercel serve HTTPS).
   - Vercel: `BACKEND_URL=https://<your-render-service>.onrender.com`.

## Deployment sequence

1. **Supabase**: create a free project, grab the connection string (direct
   connection, port 5432 — the backend holds its own long-lived pool, so the
   pgbouncer/transaction pooler used for serverless isn't needed). Run
   `uv run alembic upgrade head` and `uv run python -m scripts.seed` locally
   against that `DATABASE_URL` to create the schema and the five advocate
   logins (`backend/credentials.txt` will contain their generated passwords —
   share those with the friend out of band, don't commit the file).

2. **Render**: new Web Service from this repo, root directory `backend/`,
   Docker runtime (picks up the new Dockerfile automatically). Set the env
   vars from above. Set the health check path to the existing
   `/api/health` (`backend/app/main.py:58-60`). Deploy, then confirm
   `curl https://<service>.onrender.com/api/health` returns `{"status":"ok"}`.

3. **Vercel**: import `frontend/` as the project root, set `BACKEND_URL` to
   the Render URL from step 2, deploy.

4. **End-to-end check**: log in on the Vercel URL with a seeded advocate
   account, browse existing cases, then run one real DCMS refresh together
   with the friend — confirm the CAPTCHA image renders through the proxy,
   confirm Hearings/Court Status update and nothing else does (ADR-0002), and
   confirm both sides see the Render cold-start delay if the service had gone
   idle first.

## Verification

- `curl` the Render `/api/health` endpoint directly.
- Full login → view cases → run one live ingest flow, on the actual deployed
  URLs, with the friend solving the CAPTCHA — this is the one thing that can't
  be verified by the existing `pytest` suite, since it depends on the real
  DCMS portal and a human.
- Watch Render's logs during that first request after idle, to confirm the
  Playwright browser launches cleanly in the container (missing system
  libraries for headless Chromium are the most common failure mode here).
