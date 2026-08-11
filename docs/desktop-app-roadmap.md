# Roadmap — Windows desktop app

The execution plan for packaging DCMS as a Windows desktop app on the friend's
own laptop. Read alongside `docs/desktop-app-plan.md` (the architecture and
why each decision was made) and `docs/hosting-plan.md` (why cloud hosting was
tried first, and why it stalled). **Where this file and `desktop-app-plan.md`
disagree, the plan doc wins on architecture; this file wins on what's
actually been built.**

Tick items as they land, and add a line under *Findings* when reality
contradicts an assumption — same discipline as the main `ROADMAP.md`, for the
same reason: this is the memory between sessions.

**Status: not started.** Architecture, technology choices, and the decisions
behind them (Tauri over Docker Desktop, Windows-only, skip code-signing for
v1, public releases repo) are recorded in `docs/desktop-app-plan.md`. Nothing
below has been built yet.

---

## Rules that must not be broken

Carried over from `desktop-app-plan.md`'s decisions, restated as invariants
so a later session can't quietly relax one while iterating on the parts that
are actually hard.

1. **Chromium is never bundled by PyInstaller.** Installed lazily by
   Playwright itself on first run, same reasoning as the fix already made to
   `backend/Dockerfile` for the exact same class of bug (browser cache path
   tied to the wrong user/location). Fighting PyInstaller to embed the
   browser binary is the specific thing known to break on other platforms;
   don't reintroduce it here for convenience.
2. **Postgres stays on Supabase.** No local database, ever, for this app —
   only the browser/backend needs to run on her network.
3. **The installer is treated as a secret**, the same way
   `backend/credentials.txt` already is. It carries the Supabase DB password
   baked in. Don't post it anywhere public; if it's ever lost or shared
   beyond the one friend it's built for, rotate the DB password.
4. **No code-signing for v1.** Decided knowingly, accepting a SmartScreen
   warning on every update. Revisit only if that friction turns out worse in
   practice than expected — don't silently add it back for "polish."
5. **Update binaries are public, source is not.** The manifest and compiled
   installers live in a separate public repo; `casebook` itself stays
   private.
6. **Windows only, for now.** Don't attempt a macOS or Linux build until the
   Windows path is proven end to end — the known PyInstaller/Playwright
   bundling bug is macOS-specific, and there's no reason to take on that risk
   before this platform even works.

---

## Phase A — Frontend: standalone output

- [ ] `output: "standalone"` in `frontend/next.config.ts`
- [ ] Confirm the existing `/api/*` rewrite still works unchanged against a
      local `BACKEND_URL` under standalone mode
- [ ] Confirm the standalone build's shape (which files, `node_modules`
      pruning) is what a Tauri sidecar actually needs to run `next start`
      from

## Phase B — Backend: packaged as a native process

- [ ] PyInstaller `--onedir` spec for the FastAPI/uvicorn entrypoint
- [ ] Bake this build's production settings as defaults: `DATABASE_URL`
      (Supabase session pooler), a real `SESSION_SECRET`, `DEBUG=false`,
      `ALLOWED_ORIGINS` (exact value blocked on the open question below)
- [ ] Lazy Chromium install on first run — check
      `%LOCALAPPDATA%\casebook\ms-playwright`, run the install if empty, show
      a "Setting up (first run only)…" state in the frontend meanwhile
- [ ] Confirm the frozen exe actually launches with every real dependency:
      `uvicorn`, SQLAlchemy + `asyncpg`, `argon2-cffi` (a C extension —
      exactly the kind of thing PyInstaller hidden-import bugs like to hide
      in), Playwright's own subprocess-launching driver
- [ ] Alembic is **not** bundled — the Supabase DB is already migrated and
      seeded; the packaged app only ever connects to it, never migrates it.
      Confirm nothing in the runtime import path pulls `alembic` in anyway

## Phase C — Tauri shell

- [ ] Scaffold `src-tauri/` — first Rust/Tauri code in this repo
- [ ] Wire both sidecars (`externalBin`): the PyInstaller backend folder, a
      portable Node running the standalone Next.js build
- [ ] Startup sequence: launch both sidecars, poll the backend's
      `/api/health` and the frontend's root until both respond, then show the
      main window pointed at the frontend's local URL
- [ ] Clean shutdown: both subprocesses killed when the window closes — no
      orphaned backend process left running after she quits, matching the
      "nothing outlives the process" discipline already in
      `backend/app/dcms/{session,browser}.py`
- [ ] Resolve the exact `ALLOWED_ORIGINS` value once Tauri's webview origin
      is known for real (`tauri://localhost` vs `http://127.0.0.1:<port>`
      depend on how the window loads the frontend — confirm rather than
      guess)

## Phase D — Auto-update

- [ ] New public GitHub repo, releases only (source stays in private
      `casebook`)
- [ ] `tauri-plugin-updater` wired to that repo's `latest.json`
- [ ] Generate and safely store the update-signing keypair (Tauri's own
      update-integrity signature — separate from, and not a substitute for,
      OS-level code-signing, which is deliberately skipped per the rules
      above)
- [ ] Build/release script (or GitHub Actions workflow) that produces the
      installer + manifest and publishes them to the releases repo — this
      *is* the "ship a feature" loop once it exists

## Phase E — First real Windows build and verification

- [ ] First build attempt on actual Windows hardware — expected to surface
      something the research didn't predict; a failed first attempt is the
      expected case, not a sign of a wrong plan
- [ ] Full login → browse cases → live DCMS ingest, from the packaged app, on
      her actual residential network — the check that answers whether the
      entire pivot worked
- [ ] Ship one trivial change through the complete loop (build → public
      release → her app auto-updates) before relying on it for anything real
- [ ] Decide the fate of the existing Render + Vercel deployment (open
      question below) once this path is proven

---

## Open questions

- **What happens to Render + Vercel?** Still works for everything except live
  ingest. Leave running (free, harmless, possibly useful as a browse-only
  preview) or wind down once this app supersedes it? Not blocking the phases
  above either way.
- **Will PyInstaller `--onedir` actually work cleanly** for this dependency
  set (`asyncpg`, `argon2-cffi` as C extensions, Playwright's subprocess
  launching), or will it need the fallback discussed but not committed to:
  skip PyInstaller entirely and bundle a portable Python + the project's
  existing `uv`-managed venv directly as the sidecar? Answer by attempting
  Phase B, not by guessing further up front.
- **Will Windows Defender / other antivirus flag the PyInstaller executable
  as a false positive?** A well-known, common problem for PyInstaller-built
  apps generally, independent of the SmartScreen question already decided.
  If it happens, options include submitting the binary to Microsoft for
  reputation review — not yet investigated.
- **Does skipping code-signing prove more painful in practice than
  expected**, once the friend is actually clicking through a SmartScreen
  warning on every real update? Revisit rule 4 above if so, rather than
  living with silent frustration.

## Findings

Record answers here as they're learned, with the date — same discipline as
`ROADMAP.md`. Empty for now; nothing has been built yet.
