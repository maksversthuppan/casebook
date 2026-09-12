"""Entrypoint for the frozen desktop build.

Responsibilities `uv run uvicorn app.main:app` doesn't have, in order:

1. Point Playwright at a persistent per-user Chromium install and install it
   there if it's missing (Rule 1: Chromium is never bundled by PyInstaller -
   installed lazily by Playwright itself on first run).
2. Bake this build's production settings in, if CI generated them
   (`_defaults.py` - see that module).
3. Run uvicorn directly, in-process (no subprocess/reload - this *is* the
   process the Tauri shell launches and health-checks).
"""

import asyncio
import logging
import os
import socket
import sys
from pathlib import Path

log = logging.getLogger(__name__)

#: 127.0.0.1 only - the Tauri window is the only client, and nothing here
#: should be reachable from the rest of the friend's home network.
HOST = "127.0.0.1"
PORT = 8743


def _install_ipv4_fallback_dns() -> None:
    """Retry a failed DNS resolution with IPv4 only, Windows only.

    Unverified, instrumented fix for a login failure a real Windows build hit
    connecting to Supabase's pooler (`getaddrinfo failed`, WSAGetLastError
    11004/WSANO_DATA) - see docs/desktop-app-roadmap.md Findings, 2026-09-12+,
    for the investigation. Root cause is not confirmed; Windows Defender was
    ruled out, but why this machine's dual-stack resolution would fail for a
    host with A records and no AAAA records, when the OS's own resolver
    (`Test-NetConnection`) resolves and connects fine, is not understood -
    this exists to gather real evidence, not because the mechanism is
    verified.

    Every real event loop (`ProactorEventLoop` included) gets `getaddrinfo`
    from `BaseEventLoop`, not the `AbstractEventLoop` interface - patching
    the wrong one is a real mistake that was made and caught here (proved
    with a local repro: the patched function was simply never called).
    Falls back only on an actual `OSError` from the original, unmodified
    call, so a machine where resolution already works sees no behavior
    change at all - confirmed locally the normal case still returns both
    address families untouched.
    """
    if sys.platform != "win32":
        return

    original = asyncio.base_events.BaseEventLoop.getaddrinfo

    async def _ipv4_fallback(self, host, port, *, family=0, type=0, proto=0, flags=0):
        try:
            return await original(self, host, port, family=family, type=type, proto=proto, flags=flags)
        except OSError:
            if family != 0:
                raise
            log.warning(
                "getaddrinfo(%r, family=AF_UNSPEC) failed - retrying with "
                "AF_INET only (docs/desktop-app-roadmap.md Findings)",
                host,
            )
            return await original(
                self, host, port, family=socket.AF_INET, type=type, proto=proto, flags=flags
            )

    asyncio.base_events.BaseEventLoop.getaddrinfo = _ipv4_fallback


def _browsers_path() -> Path:
    r"""Where Chromium lives for this install, persistent across app updates.

    ``%LOCALAPPDATA%\casebook\ms-playwright`` on Windows - the only shipped
    target (Rule 6). Falls back to a dotfile under the home directory so this
    module still runs for manual smoke-testing on a non-Windows dev machine.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "casebook" / "ms-playwright"
    return Path.home() / ".casebook" / "ms-playwright"


def _ensure_chromium() -> None:
    """Install Chromium into `_browsers_path()` if it isn't there yet."""
    browsers_path = _browsers_path()
    # Must be set before anything imports playwright's async/sync API - the
    # driver resolves this env var when it first launches a browser, not
    # only at `playwright install` time.
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    if browsers_path.is_dir() and any(browsers_path.glob("chromium-*")):
        return

    print("Setting up (first run only)...", flush=True)
    browsers_path.mkdir(parents=True, exist_ok=True)

    # The `playwright install` CLI, called in-process rather than via
    # `sys.executable -m playwright` - there is no real interpreter to exec
    # inside a frozen app. `pyinstaller-hooks-contrib`'s playwright hook is
    # what makes this work frozen: it bundles the driver's Node runtime
    # (`playwright/driver/`) as binaries/data, which this CLI call shells out
    # to internally to do the actual download.
    from playwright.__main__ import main as playwright_cli

    old_argv = sys.argv
    sys.argv = ["playwright", "install", "chromium"]
    try:
        playwright_cli()
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise RuntimeError(f"chromium install failed (exit code {exc.code})") from exc
    finally:
        sys.argv = old_argv


def main() -> None:
    _install_ipv4_fallback_dns()
    _ensure_chromium()

    # Side-effecting import: sets os.environ defaults for DATABASE_URL,
    # SESSION_SECRET, etc. Must happen before app.config.get_settings() first
    # runs (it's @lru_cache'd) - which main.py triggers at import time, so
    # this import has to come before `import uvicorn` below runs the app.
    # Absent on a dev machine (gitignored, CI-generated) - that's fine, it
    # just means the ordinary .env-driven Settings defaults apply instead.
    try:
        from app.desktop import _defaults  # noqa: F401
    except ImportError:
        print(
            "app/desktop/_defaults.py not found - running with .env/Settings "
            "defaults, not the baked production config. Expected on a dev "
            "machine; not expected in a real desktop build.",
            flush=True,
        )

    import uvicorn

    # A real import, not the string form ("app.main:app") - the string form
    # makes uvicorn import the module itself at runtime, which PyInstaller's
    # static analysis (starting from this file) can't see coming and so
    # never bundles. This exact failure mode: "Error loading ASGI app. Could
    # not import module 'app.main'." - app.main was never in the build.
    from app.main import app as asgi_app

    uvicorn.run(asgi_app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
