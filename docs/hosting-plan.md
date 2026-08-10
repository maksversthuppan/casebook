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

1. **`backend/Dockerfile`** (done). Slim Python base, `uv sync --frozen
   --no-dev`, then `uv run playwright install --with-deps chromium` (installed
   at build time rather than picking a pre-built Playwright image, so the
   browser version stays in lockstep with whatever `playwright>=1.62.0`
   resolves to in `uv.lock`). Playwright's install step needs root for `apt`,
   but the running process doesn't, so the image switches to an unprivileged
   `app` user afterwards — which means the browser cache from the install step
   (`/root/.cache/ms-playwright` by default) has to be relocated first via
   `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`, chowned to `app` alongside it, or
   Chromium launches fail at runtime with "Executable doesn't exist" even
   though the build succeeded. `CMD` binds to Render's `$PORT`, not the
   hardcoded `8000` used locally: `uvicorn app.main:app --host 0.0.0.0 --port
   ${PORT:-8000}`.

2. **`backend/.dockerignore`** (done) — excludes `.venv`, `tests/`,
   `credentials.txt`, `.env`, `.git`.

3. **`backend/app/main.py` / `app/config.py`** (done) — `allow_origins` is now
   read from a new `ALLOWED_ORIGINS` env var (comma-separated, defaults to
   `http://localhost:3000`) instead of a hardcoded list, so the Vercel URL is
   a dashboard setting rather than a code change. (Low-stakes either way,
   since the browser never calls Render directly through the rewrite proxy,
   but it matters if you or the friend ever hit the Render URL directly, e.g.
   to check `/api/health`.) Also added: `get_settings()` now raises at startup
   if `DEBUG=false` but `SESSION_SECRET` is still the dev default, so a
   misconfigured deploy fails fast instead of silently signing cookies with a
   secret checked into git.

4. **No frontend code changes.** `frontend/next.config.ts` already reads
   `BACKEND_URL` from the environment — set it in Vercel's project settings.

5. **Environment variables to set** (dashboard-only, never commit):
   - Render: `DATABASE_URL` (Supabase **session pooler** connection string —
     see the IPv6 note below — keep the `postgresql+asyncpg://` prefix and
     percent-encode the password), `SESSION_SECRET` (generate with
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`, same as
     the existing `.env.example` instructions; `app/config.py` now refuses to
     start with the dev default once `DEBUG=false`, so this isn't optional),
     `DEBUG=false` (this flips `https_only=True` on the session cookie in
     `main.py:40` — required since both Render and Vercel serve HTTPS),
     `ALLOWED_ORIGINS` (comma-separated, add the Vercel URL from step 3 below
     alongside `http://localhost:3000`).
   - Vercel: `BACKEND_URL=https://<your-render-service>.onrender.com`.

## Deployment sequence

1. **Supabase**: create a free project, then grab the connection string from
   Project Settings → Database. Use the **Session pooler** string, not
   "Direct connection" — Supabase's direct-connection hostname
   (`db.<ref>.supabase.co`) now resolves IPv6-only, and most networks (this
   office included) have no IPv6 route, so `alembic upgrade head` fails with
   `OSError: Network is unreachable` against it. The session pooler
   (`aws-0-<region>.pooler.supabase.com:5432`, username
   `postgres.<project-ref>`) is IPv4-reachable and, unlike the *transaction*
   pooler, still supports the long-lived session/prepared-statement usage the
   backend's own connection pool relies on — so it's a straight swap, same
   port, same `postgresql+asyncpg://` prefix. Percent-encode the password in
   the URL (`urllib.parse.quote(pw, safe="")`) since Supabase-generated
   passwords contain characters like `%` and `/` that aren't valid unescaped
   in a URI.

   Then run `uv run alembic upgrade head` and `uv run python -m scripts.seed`
   locally against that `DATABASE_URL` to create the schema and the five
   advocate logins (`backend/credentials.txt` will contain their generated
   passwords — share those with the friend out of band, don't commit the
   file).

   Separately: `backend/alembic/env.py` passes the URL through
   `config.set_main_option`, which stores it in a `configparser` value —
   `configparser`'s interpolation treats a bare `%` as the start of a
   reference, so a percent-encoded password breaks *any* alembic command, not
   just this one. Fixed once in `env.py` by doubling literal `%` before
   setting the option; no further workaround needed here or on Render.

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
