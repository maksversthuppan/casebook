# Running DCMS as a Windows desktop app on the friend's own laptop

## Context

`docs/hosting-plan.md` covers the Vercel + Supabase + Render attempt and why
it stalled: the DCMS portal (`filing.keralacourts.in`) appears to block
cloud/datacenter IP ranges outright, confirmed two ways (a bare TCP connect
from Render's network never got a SYN-ACK; an ordinary phone browser on a
Netherlands VPN got an active `ERR_CONNECTION_RESET` on the same portal, off
VPN it worked normally). Paid residential/ISP proxy services were then
evaluated and rejected — the realistic entry cost (~$5+ minimum, recurring in
most cases) wasn't justified for a single friend's test, and coverage/quality
varies enough that it wasn't a confident fix anyway.

The alternative decided on here: run the app on the friend's own Windows
laptop. Her network is an ordinary residential/consumer connection, the same
category of network this whole project already assumes (ADR-0004: one
always-on office server, no cloud hosting in the loop) — so the portal
question goes away entirely, for free, as long as she's on a normal Indian
ISP (this is the load-bearing assumption; if her connection is ever flagged
the same way, this plan doesn't fix anything).

She isn't technical, so "run docker compose and open a terminal" isn't
viable. The goal is a normal-feeling installed app with one icon, and the
ability to ship her new features without her doing anything beyond opening
the app - an auto-updater.

Decisions made:
- **Native Tauri app**, not a Docker Desktop + shortcut approach (the other
  option considered) - more engineering effort, but a genuinely single-icon
  experience with a built-in updater, which matters more given how
  non-technical she is.
- **Windows only**, for now - matches her actual laptop, and sidesteps a real
  compatibility problem: PyInstaller bundling Playwright's Chromium binary is
  known to break on macOS ("bundle format unrecognized" in `--onefile` mode);
  Windows doesn't hit this.
- **Skip code-signing for now** - accept a Windows SmartScreen warning on
  every update, not just the first install, and walk her through it once. A
  real code-signing cert (~$100-400/yr) is the fix if this friction turns out
  to matter more than expected; revisit if so.
- **Update artifacts go in a new, separate *public* GitHub repo** - source
  stays private in `casebook`; only compiled installers + the updater
  manifest are public. Tauri's updater fetches over a plain unauthenticated
  request, which a private repo's release assets can't serve without a token.
- **Postgres stays on Supabase.** Only the browser/backend needs to run on
  her real network - the data is safer centralized (backed up, inspectable by
  you) than living solely on one laptop that might be reformatted, lost, etc.

## Target architecture

| Piece | Where | Why |
|---|---|---|
| Frontend (Next.js) | Bundled as a Tauri sidecar, `next start` on Next's **standalone** output | Keeps the existing `/api/*` rewrite-proxy design completely unchanged - zero frontend code edits |
| Backend (FastAPI + Playwright) | Bundled as a second Tauri sidecar, PyInstaller `--onedir` build | `--onedir` over `--onefile` for robustness/debuggability; the onefile-specific bundling bug is macOS-only but there's no reason to risk it |
| Chromium | **Not** bundled by PyInstaller | Installed once by Playwright itself (`playwright install chromium`) into a folder under the app's local data dir, on first launch. Avoids PyInstaller ever having to embed/introspect the Chromium binary at all - the actual source of the macOS bug, and a needless risk on Windows too |
| Database | Supabase (unchanged from hosting-plan.md) | Already provisioned, seeded, and reachable from anywhere with normal internet |
| Update distribution | New public GitHub repo, Releases only | Free, matches Tauri's own tooling (`tauri-action` generates the signed `latest.json` + uploads installer assets to a release automatically) |

The Tauri window itself just loads `http://127.0.0.1:<frontend-port>` once
both sidecars report healthy - from the friend's point of view, she opens one
app and a window appears. No terminal, no Docker, no localhost URL to know
about.

## Open question before starting

**What happens to the existing Render + Vercel deployment?** It works for
everything except live ingest (confirmed in hosting-plan.md's verification
section). Options: leave it running as-is (free, no harm, could still serve
as a login/browsing-only preview if useful), or wind it down since this
desktop app supersedes it for the actual friend test. Not blocking the work
below either way, but worth a decision so Render doesn't sit there
unmaintained and confusing later.

## Security note - read before shipping the first build

The packaged app will have `DATABASE_URL` (Supabase session-pooler
connection string, including the DB password) and `SESSION_SECRET` baked in
as defaults, since the friend won't be setting environment variables herself.
**A PyInstaller bundle is not obfuscation - anyone with the installer file can
extract those strings from it with basic tools.** This is an acceptable
tradeoff only because the app is going to exactly one named, trusted person
for a defined test, matching the "real case data is fine for this test"
decision already made in `docs/hosting-plan.md`. Concretely:

- Treat the built installer the same way `backend/credentials.txt` is already
  treated - hand it to her directly, don't post it anywhere public (the
  public releases repo holds the installer for the *updater* to fetch
  automatically once she's already running the app, which is a different
  thing from posting a first-install link somewhere open).
- If the installer is ever shared beyond her, or the laptop is lost/stolen,
  **rotate the Supabase DB password** (regenerate in the Supabase dashboard,
  update `DATABASE_URL` in the next release) - treat it as leaked the moment
  distribution control is lost, the same way a checked-in secret would be.
- `SESSION_SECRET` leaking is lower-stakes (it only signs her own local
  session cookie) but gets rotated for free whenever the DB password is
  rotated anyway, so no separate handling needed.

## Implementation steps

1. **Frontend: switch to Next's `standalone` output.** Add `output:
   "standalone"` to `frontend/next.config.ts`. This produces a minimal
   self-contained server bundle (a handful of files plus a pruned
   `node_modules`) rather than needing the full dev toolchain at runtime -
   built specifically for exactly this kind of embedded-server packaging.
   Everything else about the frontend (the `/api/*` rewrite, all pages)
   stays as-is; `BACKEND_URL` just points at `http://127.0.0.1:<port>`
   instead of the Render URL.

2. **Backend: PyInstaller spec.** `--onedir` build of the FastAPI app
   (`uvicorn` entrypoint), targeting Windows. Bake in the production
   settings (`DATABASE_URL`, a real `SESSION_SECRET`, `DEBUG=false`,
   `ALLOWED_ORIGINS=http://127.0.0.1:<frontend-port>` - or `tauri://localhost`
   depending on how Tauri serves the window, needs confirming once the
   window's origin is known) as defaults rather than requiring a `.env` file
   on her machine.

3. **Backend: lazy Chromium install.** On startup, before launching uvicorn,
   check whether Chromium exists under `PLAYWRIGHT_BROWSERS_PATH` (set to
   somewhere under `%LOCALAPPDATA%`); if not, run the equivalent of
   `playwright install chromium` once and show a "Setting up (first run
   only)..." state in the frontend while that happens. Needs internet on
   first run only, same as installing any app.

4. **Tauri project scaffold** (`src-tauri/`), configured with two
   `externalBin` sidecars (the PyInstaller backend folder, a portable Node +
   the standalone Next.js build). Startup sequence: launch both sidecars,
   poll the backend's `/api/health` and the frontend's root until both
   respond, then show the main window pointed at the frontend's local URL.
   Shutdown: kill both sidecar processes when the window closes - no orphaned
   background processes left running after she quits, matching the existing
   "nothing outlives the process" discipline already in
   `backend/app/dcms/session.py`/`browser.py`.

5. **Auto-updater.** Add `tauri-plugin-updater`, pointed at the public
   releases repo's `latest.json`. Build/release flow: a script (or GitHub
   Actions workflow) in `casebook` that runs the Tauri build and pushes the
   resulting installer + manifest to the public repo's Releases - this is
   the whole "ship a feature" loop once set up: build, push, her app picks it
   up next launch.

6. **First real Windows build and install**, on this machine or a Windows
   box, to catch anything the research above didn't - PyInstaller/Playwright
   interaction issues are common enough in the wild that a first attempt
   failing is the expected case, not a sign the plan is wrong.

## Verification

- Backend sidecar's `/api/health` responds once both processes are up.
- A full login → browse cases → live DCMS ingest run, from the packaged app
  on an actual Windows machine on a normal Indian residential connection -
  this is the check that answers whether the entire pivot worked, same as
  the equivalent check in `hosting-plan.md` was meant to for Render.
- Ship one trivial follow-up change (e.g. a label tweak) through the full
  build → public-repo-release → her-app-updates loop, end to end, before
  relying on it for anything real.
