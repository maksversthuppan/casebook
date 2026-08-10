"""One shared browser for the process; one isolated context per portal session.

A context per session matters rather than being tidy: the CAPTCHA is bound to
the session that fetched it, so two advocates refreshing at the same time must
not share cookies.
"""

import asyncio
import logging

from playwright.async_api import Browser, Playwright, async_playwright

log = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None
_lock = asyncio.Lock()


async def get_browser() -> Browser:
    """Start Playwright on first use, not at boot.

    Most of the day nobody refreshes anything, and an idle office server should
    not be holding a browser open for it.
    """
    global _playwright, _browser

    async with _lock:
        if _browser is not None and _browser.is_connected():
            return _browser

        if _playwright is None:
            _playwright = await async_playwright().start()

        log.info("starting chromium for DCMS")
        _browser = await _playwright.chromium.launch(headless=True)
        return _browser


async def shutdown() -> None:
    """Called from the application lifespan. Nothing may outlive the process."""
    global _playwright, _browser

    async with _lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
