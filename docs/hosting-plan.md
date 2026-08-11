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

## Finding: the DCMS portal is unreachable from Render entirely

Everything above works — login, session cookies, the proxy, the database. The
one thing that doesn't is the ingest/refresh flow itself: `POST
/api/ingest/start` reliably fails after exactly 45 seconds with

```
could not navigate to the DCMS portal: TimeoutError('Page.goto: Timeout 45000ms exceeded.
Call log:
  - navigating to "https://filing.keralacourts.in/caseSearch", waiting until "domcontentloaded"
')
```

(That message only exists because `backend/app/dcms/portal.py`'s `open_search`
now logs the real exception before converting it to the plain sentence the
advocate sees — it didn't originally, and the advocate-facing 502 alone gives
no way to tell a portal timeout apart from anything else.)

What rules out the obvious explanations:

- **Not a Vercel/proxy timeout.** Hitting `https://<service>.onrender.com/api/ingest/start`
  directly (bypassing the Vercel rewrite entirely) times out identically.
- **Not a cold start.** The same failure happens on a warm service.
- **Not the Render region.** The service was already on Render's Singapore
  region — the closest to India on offer — before this was investigated.
- **Not DNS, not a TLS error, not an HTTP-level rejection (403/429/etc).** All
  of those surface as a fast, specific `net::ERR_...` from Chromium. What
  actually happens is a silent hang for the *entire* 45-second budget with no
  underlying error at all — the signature of packets being dropped outright
  somewhere upstream of the portal, not answered.
- **Not a missing/wrong `User-Agent`.** `backend/app/dcms/session.py:33-36`
  already sends an ordinary desktop Chrome UA string on every session — this
  was already required knowledge before any of this hosting work started
  (`backend/scripts/probe_portal.py:39-40`: "The portal refuses connections
  outright to clients whose user agent looks automated. This is not
  optional"), and it's already in the code path `ingest.py` uses.

Curling the same URL from an ordinary Kerala residential connection (Airtel
broadband) returns `200` in half a second. So the portal — or, more likely,
something in front of it (a WAF, or the state/NIC network edge) — appears to
treat Render's outbound IP ranges categorically differently from a normal ISP
connection.

**What this does and doesn't tell us:** it's consistent with either (a) a
blanket IP/ASN-based block on "cloud/datacenter" address space, independent of
which region or provider, or (b) a TLS/JA3-level fingerprint check on
Chromium's handshake specifically, independent of the `User-Agent` header
(headless-Chromium's TLS ClientHello can differ from a real browser's even
when every HTTP-visible header is spoofed correctly). Both produce the exact
same silent-hang symptom, so the log line above doesn't distinguish them.
Telling them apart would need one more probe not yet run: a plain, non-browser
HTTPS request (e.g. `httpx.get(...)`) to the same URL from inside the same
Render container. If that also hangs, it's (a); if it succeeds, it's (b) and
worth trying a stealth-patched Chromium before moving infrastructure at all.
That probe requires a temporary script deployed to Render to actually
execute from Render's network — not yet done.

Regardless of which it is, redeploying to a different cloud region is unlikely
to help: every option on Render (and the equivalent on AWS/GCP/Azure/Oracle,
India regions included) is still cloud/datacenter address space, and if the
block is ASN-based rather than country-based, an India-region cloud VM is
still exactly the kind of address the block is likely keying on.

## Alternative backend host: Cloudflare Tunnel from a real Indian network

The one network path already *proven* to reach the portal normally (0.5s,
`200`) is an ordinary residential/office Kerala connection — because that's
what this whole project was built to run from (ADR-0004: one always-on office
server). Rather than gambling on a different cloud region, the cheapest fix
that's actually certain to work is to run the backend on a machine that's
already on such a connection, and expose it to the internet with
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) —
free, no port-forwarding, no static IP or router configuration needed, since
the tunnel daemon (`cloudflared`) only ever makes an *outbound* connection to
Cloudflare.

The frontend doesn't move — it stays on Vercel exactly as deployed. Only
`BACKEND_URL` changes, from the Render URL to the tunnel's.

### Option A — Quick Tunnel (zero setup, URL changes every time)

No Cloudflare account needed. Good for a single testing session; the URL is
random and only lives as long as the `cloudflared` process does, so it's the
wrong choice for anything you want to come back to later without redoing step 4.

1. Install `cloudflared` on the machine that will run the backend (the office
   machine, or this one):

   ```bash
   # Debian/Ubuntu
   curl -L --output cloudflared.deb \
     https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```

2. Run the backend container with the production env vars (same values
   already used on Render — Supabase session-pooler `DATABASE_URL`, a real
   `SESSION_SECRET`, `DEBUG=false`, `ALLOWED_ORIGINS` including the Vercel
   URL):

   ```bash
   cd backend
   docker build -t casebook-backend .
   docker run -d --name casebook-backend --restart unless-stopped \
     -p 8000:8000 \
     -e DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<url-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres" \
     -e SESSION_SECRET="<generate with: python -c \"import secrets; print(secrets.token_urlsafe(48))\">" \
     -e DEBUG=false \
     -e ALLOWED_ORIGINS="http://localhost:3000,https://casebook-drab.vercel.app" \
     casebook-backend
   ```

3. Start the tunnel, pointing at that container's port:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

   It prints a URL like `https://random-words-here.trycloudflare.com`. Confirm
   it works before wiring up Vercel:

   ```bash
   curl https://random-words-here.trycloudflare.com/api/health
   ```

4. Point Vercel at it:

   ```bash
   cd frontend
   vercel env rm BACKEND_URL production   # remove the old Render value
   printf 'https://random-words-here.trycloudflare.com' | vercel env add BACKEND_URL production
   vercel --prod
   ```

5. Both the `docker run` container and the `cloudflared tunnel` process must
   keep running for the friend to use ingest. If either is restarted, the
   `trycloudflare.com` URL changes and step 4 has to be redone.

### Option B — Named Tunnel (stable URL, needs a domain in Cloudflare)

Worth it if this will be used across more than one sitting. Requires a domain
managed through Cloudflare's free DNS (either one you already own, pointed at
Cloudflare's nameservers, or a cheap new one — this is the only part of this
whole setup with any real chance of a dollar cost, and only if you don't
already have a domain).

1. `cloudflared tunnel login` — opens a browser, pick the domain (zone) to
   authorize.
2. `cloudflared tunnel create casebook-backend` — creates the tunnel and a
   credentials file, and prints a tunnel ID.
3. Create `~/.cloudflared/config.yml`:

   ```yaml
   tunnel: <TUNNEL_ID>
   credentials-file: /home/<you>/.cloudflared/<TUNNEL_ID>.json
   ingress:
     - hostname: casebook-api.yourdomain.com
       service: http://localhost:8000
     - service: http_status:404
   ```

4. `cloudflared tunnel route dns casebook-backend casebook-api.yourdomain.com`
   — creates the DNS record pointing that hostname at the tunnel.
5. Run it in the foreground once to confirm (`cloudflared tunnel run
   casebook-backend`), then install it as a persistent background service so
   it survives reboots: `sudo cloudflared service install` (reads the same
   `config.yml`).
6. Point Vercel's `BACKEND_URL` at `https://casebook-api.yourdomain.com` —
   this one doesn't need to change again as long as the tunnel keeps running.

### Notes

- Traffic between a browser and Cloudflare's edge is HTTPS via Cloudflare's
  own certificate — no cert to manage. Traffic between `cloudflared` and the
  local container is plain HTTP over `localhost`, which is fine: it never
  leaves the machine.
- `cloudflared` only opens an outbound connection *to* Cloudflare — nothing
  needs to be opened on the office router/firewall, which is a smaller attack
  surface than traditional port-forwarding would be.
- This reintroduces the exact dependency ADR-0004 already accepted: the
  backend needs a specific machine to be on and connected. That machine can be
  this same one; it just has to stay running (and not sleep) while the friend
  is testing ingest.
- `ALLOWED_ORIGINS` and every other backend env var stay exactly as they were
  for Render — only the transport in front of the container changed.
