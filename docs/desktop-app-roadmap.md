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

**Status: Phase A done (2026-08-11). Phases B, C and a first pass at D written
(2026-09-11), unverified — nothing has actually run on Windows yet.**
Architecture, technology choices, and the decisions behind them (Tauri over
Docker Desktop, Windows-only, skip code-signing for v1, public releases repo)
are recorded in `docs/desktop-app-plan.md`. B (PyInstaller) and C (Tauri
shell) are Windows-native work this dev machine can't run directly - resolved
by using a `windows-latest` GitHub Actions runner as the Windows box instead
(`.github/workflows/desktop-build.yml`), triggered manually
(`workflow_dispatch`) and producing a private build artifact, not yet the
public releases-repo flow Phase D describes. First real run is the next step;
see Findings below for what could and couldn't be checked before that.

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

- [x] `output: "standalone"` in `frontend/next.config.ts`
- [x] Confirm the existing `/api/*` rewrite still works unchanged against a
      local `BACKEND_URL` under standalone mode
- [x] Confirm the standalone build's shape (which files, `node_modules`
      pruning) is what a Tauri sidecar actually needs to run `next start`
      from

## Phase B — Backend: packaged as a native process

- [x] PyInstaller `--onedir` spec for the FastAPI/uvicorn entrypoint —
      `backend/casebook.spec`, entry `backend/app/desktop/entrypoint.py`.
      Verified with a Linux `--onedir` build (2026-09-12 Finding) after
      fixing the `app.main` import bug the first real Windows attempt
      surfaced - the frozen exe starts, installs Chromium, and answers
      `/api/health`. Still not run through the actual Windows/NSIS path
- [x] Bake this build's production settings as defaults: `DATABASE_URL`
      (Supabase session pooler), a real `SESSION_SECRET`, `DEBUG=false`,
      `ALLOWED_ORIGINS` (exact value blocked on the open question below) —
      `.github/workflows/desktop-build.yml` generates
      `backend/app/desktop/_defaults.py` (gitignored) from repo secrets
      `DESKTOP_DATABASE_URL` / `DESKTOP_SESSION_SECRET` right before the
      PyInstaller step; shape documented in `_defaults.example.py`. Secrets
      added to the repo 2026-09-12 - unverified that the values themselves
      are correct until a build actually connects to Supabase with them
- [x] Lazy Chromium install on first run — written in
      `entrypoint.py::_ensure_chromium`, using `PLAYWRIGHT_BROWSERS_PATH` +
      an in-process call to `playwright.__main__.main(["install", "chromium"])`
      (no real interpreter to `sys.executable -m playwright` inside a frozen
      app), relying on `pyinstaller-hooks-contrib`'s playwright hook to
      bundle the driver's Node runtime as a binary, not just data. **This was
      Phase B's single riskiest guess, and it's now confirmed working** - the
      2026-09-12 Linux `--onedir` test actually downloaded Chromium,
      Chromium Headless Shell and FFmpeg through this exact path, and a
      second run correctly skipped the download. Windows is still unverified
      (different OS-level install/permissions behavior is possible), but the
      core mechanism is sound. No separate "Setting up…" frontend state
      built - the window simply doesn't appear until the health check passes
      (Phase C), so the delay reads as a slow launch, not a stuck one;
      revisit only if that reads badly in practice
- [x] Confirm the frozen exe actually launches with every real dependency:
      `uvicorn`, SQLAlchemy + `asyncpg`, `argon2-cffi` (a C extension —
      exactly the kind of thing PyInstaller hidden-import bugs like to hide
      in), Playwright's own subprocess-launching driver — confirmed on Linux
      (2026-09-12); the `hiddenimports` list in `casebook.spec` turned out to
      not even be the load-bearing part (see Findings - the real bug was a
      missing *real* import of `app.main` itself). Windows-specific DLL
      issues (a different class of PyInstaller problem than missing Python
      hidden imports) are still unverified
- [x] Alembic is **not** bundled — confirmed nothing under `backend/app/`
      imports `alembic` (only `alembic.ini`/`migrations/` at the repo root do,
      and PyInstaller's entry point never touches them); `excludes=["alembic"]`
      added to `casebook.spec` as a backstop

## Phase C — Tauri shell

- [x] Scaffold `src-tauri/` — first Rust/Tauri code in this repo. Uses
      Tauri v2. `cargo check` passes on Linux (with the desktop GTK/dbus dev
      packages installed) — real coverage for the code's own logic, but not
      for the actual Windows bundle target, which only CI can build
- [ ] Wire both sidecars — **not** `externalBin`: both the backend
      (`--onedir`, many files) and the frontend (portable Node +
      the standalone folder tree) are folder trees, not the single
      self-contained binary `externalBin`/sidecar expects. Bundled instead
      as plain Tauri `resources` (`tauri.conf.json`) and spawned directly
      with `std::process::Command` in `src-tauri/src/main.rs` — a deliberate
      deviation from this file's original wording, not an oversight
- [ ] Startup sequence: launch both sidecars, poll the backend's
      `/api/health` and the frontend's root until both respond, then show the
      main window pointed at the frontend's local URL — written in
      `main.rs`; `app.windows` is empty in `tauri.conf.json` so no window
      (and no connection-refused flash) exists before both checks pass
- [ ] Clean shutdown: both subprocesses killed when the window closes — no
      orphaned backend process left running after she quits, matching the
      "nothing outlives the process" discipline already in
      `backend/app/dcms/{session,browser}.py` — written, via `RunEvent::Exit`
      in `main.rs`
- [x] Resolve the exact `ALLOWED_ORIGINS` value — resolved, and turns out
      not to matter much: the webview loads the frontend sidecar's own URL
      directly (`http://127.0.0.1:3100`, not `tauri://localhost`), and the
      browser/webview never calls the backend directly at all — the
      Next.js server does, server-to-server, which browser CORS doesn't
      govern. `ALLOWED_ORIGINS` is set to `http://127.0.0.1:3100` in
      `_defaults.example.py` as a reasonable value for anything that does
      hit the backend directly, but nothing in the normal request path needs
      it to be exactly right

## Phase D — Auto-update

- [ ] New public GitHub repo, releases only (source stays in private
      `casebook`) — deliberately **not** done yet. This first build is a
      private test for one person, and the plan's own security note says to
      hand a first build directly rather than post it anywhere, even the
      updater's public repo — see `desktop-build.yml`'s private Actions
      artifact instead
- [ ] `tauri-plugin-updater` wired to that repo's `latest.json`
- [ ] Generate and safely store the update-signing keypair (Tauri's own
      update-integrity signature — separate from, and not a substitute for,
      OS-level code-signing, which is deliberately skipped per the rules
      above)
- [ ] Build/release script (or GitHub Actions workflow) that produces the
      installer + manifest and publishes them to the releases repo — partial:
      `.github/workflows/desktop-build.yml` produces the installer (manual
      `workflow_dispatch`, uploaded as a private Actions artifact), but there
      is no manifest and nothing publishes to a releases repo yet - that's
      the rest of this phase, once the repo above exists. This
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
- **`DESKTOP_DATABASE_URL` / `DESKTOP_SESSION_SECRET` repo secrets don't
  exist yet.** `.github/workflows/desktop-build.yml` refuses to run without
  them (fails fast with an explanatory error rather than baking in a
  placeholder). Someone with the Supabase dashboard needs to add them under
  the repo's Settings → Secrets → Actions before the workflow can produce a
  real build - `DESKTOP_DATABASE_URL` is the full `postgresql+asyncpg://...`
  session-pooler connection string, `DESKTOP_SESSION_SECRET` any long random
  string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

## Findings

Record answers here as they're learned, with the date — same discipline as
`ROADMAP.md`.

- **2026-08-11 — Phase A done, and testable on Ubuntu without a Windows box.**
  `next build` with `output: "standalone"` is cross-platform: it produces a
  plain Node server (`.next/standalone/server.js`), and `next start`'s
  behavior — including the `/api/*` rewrite — doesn't depend on the OS.
  Verified end to end on this machine: built the frontend, copied
  `public/` and `.next/static/` into the standalone folder (required manually
  — `server.js` doesn't serve either by default, per Next's own docs), ran
  `BACKEND_URL=http://localhost:8000 PORT=3100 node .next/standalone/server.js`
  against the real backend (`uv run uvicorn app.main:app --port 8000`), and
  confirmed `/api/health` proxies through correctly, static assets
  (`/next.svg`) serve, and a client route (`/login`) renders. No frontend
  code changes were needed beyond the one config line, as the plan predicted.
  The standalone folder shape is flat (`server.js`, `.next/`, `node_modules/`,
  `package.json` all at one level) since `frontend/` is the Next.js project
  root — no monorepo nesting to account for in the Phase C sidecar wiring.
- **2026-08-11 — the standalone trace pulls in a platform-specific native
  binary the app doesn't even use.** `.next/standalone/node_modules/@img/`
  contains `sharp-linux-x64` (built for *this* Ubuntu machine) even though
  nothing in `frontend/src` imports `next/image` — Next bundles `sharp`
  defensively for the `/_next/image` optimization route regardless of actual
  usage. Harmless for this test (never invoked), but it means **the
  standalone build is not portable across OSes as produced here** — a
  Windows Tauri sidecar needs its own `npm install` (or at minimum the
  `@img/sharp-win32-x64` optional dep) run on/for Windows, not this Linux
  build copied over. Matches rule 6 (Windows-only builds happen on Windows)
  and is one more reason Phase B/C can't be faked on this machine — noting it
  now so nobody assumes the frontend half of the sidecar can be prepped here
  and just handed to Tauri on Windows unchanged.
- **2026-09-11 — a `windows-latest` GitHub Actions runner stands in for the
  Windows box Phase B/C need.** Rather than wait for physical/VM Windows
  access, `.github/workflows/desktop-build.yml` does the whole build there:
  frontend standalone build (with a portable Node.exe copied in next to
  `server.js`, since the target machine has no Node installed), backend
  PyInstaller `--onedir` build, both assembled as `src-tauri/resources/*`,
  then `tauri build`. Triggered manually, produces a private Actions
  artifact. This also resolves the prior sharp/`@img` finding automatically
  — the frontend `npm ci`/`npm run build` now happens on Windows, for
  Windows, not copied over from this Linux machine.
- **2026-09-11 — sidecars are plain Tauri `resources` + `std::process::Command`,
  not `externalBin`.** `externalBin` (Tauri's sidecar mechanism) expects one
  self-contained binary named `<name>-<target-triple>(.exe)`; both halves
  here are folder trees (PyInstaller `--onedir`'s DLLs/support files; the
  standalone Next build's `.next/`, `node_modules/`, plus the portable
  `node.exe`). Bundled instead as `bundle.resources` in `tauri.conf.json`,
  spawned directly in `src-tauri/src/main.rs` via `std::process::Command`
  against paths resolved from `app.path().resource_dir()`. No window is
  created (`app.windows: []`) until both sidecars answer their health check,
  polled from a background thread; the window is then built via
  `WebviewWindowBuilder` on the main thread (`AppHandle::run_on_main_thread`)
  pointed at the frontend sidecar's own `http://127.0.0.1:3100` — never
  `tauri://localhost`, which resolved the Phase C open question about
  `ALLOWED_ORIGINS` as a side effect (see Phase C above).
- **2026-09-11 — the frozen-Chromium-install approach is written but is the
  one piece of this whole plan with no independent confirmation it works.**
  `entrypoint.py` calls `playwright.__main__.main(["install", "chromium"])`
  in-process, relying on `pyinstaller-hooks-contrib`'s playwright hook to
  have bundled the driver's Node runtime as an executable binary rather than
  inert data (which would make it non-executable once frozen). This is the
  documented community pattern, but it's never been run here — no Windows
  box, and this specific interaction is exactly the kind of thing the
  existing "will PyInstaller `--onedir` work cleanly" open question already
  flagged as answerable only by attempting Phase B for real.
- **2026-09-11 — Rust code was `cargo check`-able on Linux, PyInstaller's
  output was not.** Installed a local Rust toolchain (rustup, stable) and
  the Linux GTK/webkit2gtk/dbus dev packages Tauri needs even just to
  typecheck, and got a clean `cargo check` for `src-tauri` — real coverage
  for `main.rs`'s own logic (process spawning, health polling, window
  creation, shutdown), though not for the Windows-specific NSIS bundle step,
  which only CI can exercise. PyInstaller has no equivalent local check at
  all: it doesn't cross-compile, so `casebook.spec` and `entrypoint.py` are
  syntax-checked only, not run, until the workflow does.
- **2026-09-12 — that `cargo check` actually failed the first time, and was
  worth running.** Two real bugs, both fixed:
  - `ureq` 2.12's `Request` has one `.timeout()`, not the `.timeout_connect()`
    / `.timeout_read()` pair `main.rs` was first written with - the API
    lookup that produced those names was apparently for a different `ureq`
    version.
  - The generated icons failed tauri-codegen's PNG loader ("icon ... is not
    RGBA") despite `identify` calling them `PaletteAlpha`, because
    ImageMagick 6's default PNG writer silently re-encodes a low-color-count
    image as an indexed/palette PNG even when told `PNG32:`/`color-type=6` -
    `identify -verbose`'s "Type" field describes the decoded image's
    apparent color count, not the on-disk PNG color-type byte tauri-codegen
    actually checks (verified by reading the IHDR chunk directly). Re-forced
    with `-type TrueColorAlpha PNG32:` and confirmed via the IHDR bytes, not
    `identify`, this time.
  Neither would have surfaced without a real compiler in the loop - a good
  argument for not skipping this step on a future change to `src-tauri/`,
  even though it still can't validate the Windows-only bundle step.
- **2026-09-12 — first real Windows build attempt, and it failed exactly as
  expected: `Error loading ASGI app. Could not import module "app.main"`.**
  Root cause: `entrypoint.py` called `uvicorn.run("app.main:app", ...)` - the
  *string* form, which makes uvicorn import that module itself at runtime.
  PyInstaller's static analysis (starting from `entrypoint.py`) never saw a
  real `import` of `app.main` anywhere, so neither it nor anything FastAPI
  related under it was ever bundled - `casebook.spec`'s `hiddenimports` for
  the individual routers didn't help, because the parent module itself was
  missing, not just some of its children. Fixed by importing the app object
  directly (`from app.main import app as asgi_app`) and passing that object
  to `uvicorn.run`, not a string.
- **2026-09-12 — the fix was verified with a Linux `--onedir` build, not
  guessed at.** PyInstaller doesn't cross-compile, but running
  `uv run pyinstaller casebook.spec` **on Linux** exercises the exact same
  import-discovery logic that broke on Windows, so it's a real test of the
  fix, not just of "does this look right." Result, end to end: the frozen
  exe started, `_ensure_chromium` correctly detected no existing install and
  ran the real `playwright install chromium` path in-process (downloading
  Chrome for Testing, Chrome Headless Shell, and FFmpeg without issue -
  **this resolves Phase B's single riskiest open question**: the frozen
  Chromium install genuinely works, at least via
  `pyinstaller-hooks-contrib`'s playwright hook on this platform), then
  uvicorn started and `/api/health` answered `200 {"status": "ok"}`. A
  second run correctly skipped the download (found the existing
  `chromium-*` directory) and went straight to trying to bind the port.
  Windows-specific risks (DLLs, the NSIS bundle step, antivirus) are still
  unverified - this only proves the *Python side* of Phase B is sound, on
  any platform.
