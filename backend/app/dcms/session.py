"""Live portal sessions, one per in-flight ingestion or refresh.

Held in memory rather than in the database on purpose: a session is a live
browser context, and it means nothing after a restart. What survives is the
Snapshot it produces.

Advocates walk away from half-finished refreshes. Every session therefore has an
idle deadline and is swept, because a leaked browser context is a leaked
several-hundred megabytes.
"""

import asyncio
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from playwright.async_api import BrowserContext, Page

from app.dcms.browser import get_browser
from app.models.enums import SearchMode

log = logging.getLogger(__name__)

#: How long a session may sit untouched before it is closed. Long enough for an
#: advocate to be interrupted mid-refresh, short enough not to hoard memory.
IDLE_TIMEOUT = timedelta(minutes=10)

#: How often the sweeper looks for abandoned sessions.
SWEEP_INTERVAL_SECONDS = 60

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


@dataclass
class PortalSession:
    id: str
    advocate_id: uuid.UUID
    context: BrowserContext
    page: Page
    created_at: datetime
    last_used_at: datetime

    #: What was actually chosen in the portal's own dropdowns. Recorded verbatim
    #: so a Court can be completed from it (ADR-0005).
    state: str | None = None
    district: str | None = None
    court: str | None = None

    #: Set when this session is a Refresh of a Case that already exists, rather
    #: than an Ingestion. The two are the same act (CONTEXT.md, "Ingestion");
    #: this is the only thing that distinguishes them here.
    case_id: uuid.UUID | None = None

    #: What is being searched for, once the identifier step has been done.
    search_mode: "SearchMode | None" = None
    search_value: str | None = None
    #: Only set for the Case No / Filing No tabs; kept so a Snapshot records
    #: exactly what was searched, not just the number.
    search_case_type: str | None = None
    search_year: str | None = None

    #: Set once a search has been submitted and a response captured.
    raw_response: str | None = field(default=None, repr=False)
    #: The Snapshot the search produced, so `/review` knows which one to decide.
    snapshot_id: uuid.UUID | None = None

    def touch(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) - self.last_used_at > IDLE_TIMEOUT


class SessionExpired(Exception):
    """The session is gone - swept, closed, or never existed."""


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, PortalSession] = {}
        self._sweeper: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def open(self, advocate_id: uuid.UUID) -> PortalSession:
        browser = await get_browser()
        context = await browser.new_context(
            viewport={"width": 1500, "height": 1000}, user_agent=USER_AGENT
        )
        page = await context.new_page()

        now = datetime.now(timezone.utc)
        session = PortalSession(
            id=secrets.token_urlsafe(18),
            advocate_id=advocate_id,
            context=context,
            page=page,
            created_at=now,
            last_used_at=now,
        )

        async with self._lock:
            self._sessions[session.id] = session
        self._ensure_sweeper()
        log.info("portal session %s opened", session.id)
        return session

    async def get(self, session_id: str, advocate_id: uuid.UUID) -> PortalSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionExpired("That refresh has ended. Start it again.")
        # Sessions are not shared: the CAPTCHA one advocate is looking at belongs
        # to their browser context alone.
        if session.advocate_id != advocate_id:
            raise SessionExpired("That refresh belongs to someone else.")
        if session.expired:
            await self.close(session_id)
            raise SessionExpired("That refresh timed out. Start it again.")
        session.touch()
        return session

    async def close(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return
        try:
            await session.context.close()
        except Exception:  # noqa: BLE001 - closing must never raise onward
            log.warning("failed closing context for session %s", session_id, exc_info=True)
        log.info("portal session %s closed", session_id)

    async def sweep(self) -> int:
        stale = [sid for sid, s in list(self._sessions.items()) if s.expired]
        for sid in stale:
            log.info("sweeping abandoned portal session %s", sid)
            await self.close(sid)
        return len(stale)

    def _ensure_sweeper(self) -> None:
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.create_task(self._sweep_forever())

    async def _sweep_forever(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            try:
                await self.sweep()
            except Exception:  # noqa: BLE001 - the sweeper must not die
                log.exception("session sweep failed")

    async def shutdown(self) -> None:
        if self._sweeper is not None:
            self._sweeper.cancel()
            self._sweeper = None
        for sid in list(self._sessions):
            await self.close(sid)

    @property
    def count(self) -> int:
        return len(self._sessions)


registry = SessionRegistry()
