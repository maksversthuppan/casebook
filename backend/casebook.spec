# PyInstaller --onedir spec (docs/desktop-app-roadmap.md Phase B).
#
# PyInstaller does not cross-compile: this must be run on Windows, for
# Windows. `.github/workflows/desktop-build.yml` does that on a windows-latest
# runner. To try it manually on a Windows box instead:
#   uv sync --group desktop
#   uv run pyinstaller casebook.spec --noconfirm
#
# --onedir, not --onefile: robustness/debuggability (docs/desktop-app-plan.md)
# - the onefile-specific Playwright bundling bug this project is avoiding is
#   macOS-only, but there's no reason to take on onefile's extra risk anyway.

from pathlib import Path

a = Analysis(
    ["app/desktop/entrypoint.py"],
    pathex=[str(Path(SPECPATH))],
    binaries=[],
    datas=[],
    hiddenimports=[
        # uvicorn picks these by name at runtime; PyInstaller's static
        # import scan can't see that and drops them without this list.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # C extensions - exactly the kind of hidden import PyInstaller
        # misses (Phase B checklist).
        "asyncpg.pgproto.pgproto",
        "argon2",
        "_cffi_backend",
        "email_validator",
        # zoneinfo's fallback for the IANA tz database (app/config.py's IST)
        # is a dynamic import inside the stdlib, invisible to static
        # analysis - the exact same class of bug as the app.main fix above,
        # caught on the first real Windows run (docs/desktop-app-roadmap.md
        # Findings, 2026-09-12). pyinstaller-hooks-contrib has a hook for it
        # once it's listed here.
        "tzdata",
        # FastAPI routers are imported by app.main, not discovered by name -
        # should already be picked up transitively, listed for safety since
        # this is the one thing Phase E can't cheaply re-verify without a
        # full Windows round-trip.
        "app.api.auth",
        "app.api.cases",
        "app.api.clerks",
        "app.api.courts",
        "app.api.ingest",
        "app.api.parties",
        "app.api.record",
        "app.api.refresh",
        "app.api.search",
    ],
    hookspath=[],
    # Never bundled or run - the Supabase DB is already migrated and seeded;
    # this app only ever connects to it (Phase B checklist).
    excludes=["alembic"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="casebook-backend",
    # No console window: src-tauri/src/main.rs redirects this process's
    # stdout/stderr to a log file at spawn time (real file handles, not an
    # inherited console), and shows startup progress - including the
    # first-run "Setting up..." wait entrypoint.py used to print - in its own
    # splash window instead, read from entrypoint.py's status file.
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="casebook-backend",
)
