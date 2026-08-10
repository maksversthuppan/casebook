"""Session lifecycle.

No portal involved: these are about not leaking browser contexts when an
advocate walks away mid-refresh, which is the failure mode a server-side browser
introduces (ADR-0004).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.dcms.session import IDLE_TIMEOUT, PortalSession, SessionExpired, SessionRegistry


class FakeContext:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_session(registry: SessionRegistry, advocate_id: uuid.UUID, *, idle: timedelta | None = None):
    now = datetime.now(timezone.utc)
    context = FakeContext()
    session = PortalSession(
        id=f"s-{uuid.uuid4().hex[:8]}",
        advocate_id=advocate_id,
        context=context,  # type: ignore[arg-type]
        page=None,  # type: ignore[arg-type]
        created_at=now,
        last_used_at=now - (idle or timedelta()),
    )
    registry._sessions[session.id] = session
    return session, context


async def test_a_session_is_returned_to_its_owner():
    registry = SessionRegistry()
    who = uuid.uuid4()
    session, _ = make_session(registry, who)
    assert (await registry.get(session.id, who)).id == session.id


async def test_another_advocate_cannot_take_over_a_session():
    """The CAPTCHA on screen belongs to one browser context and one person."""
    registry = SessionRegistry()
    session, _ = make_session(registry, uuid.uuid4())
    with pytest.raises(SessionExpired):
        await registry.get(session.id, uuid.uuid4())


async def test_an_unknown_session_is_refused():
    registry = SessionRegistry()
    with pytest.raises(SessionExpired):
        await registry.get("no-such-session", uuid.uuid4())


async def test_an_abandoned_session_expires_and_is_closed():
    registry = SessionRegistry()
    who = uuid.uuid4()
    session, context = make_session(registry, who, idle=IDLE_TIMEOUT + timedelta(minutes=1))

    with pytest.raises(SessionExpired):
        await registry.get(session.id, who)

    assert context.closed, "the browser context must be closed, not merely forgotten"
    assert registry.count == 0


async def test_the_sweeper_closes_only_stale_sessions():
    registry = SessionRegistry()
    who = uuid.uuid4()
    fresh, fresh_ctx = make_session(registry, who)
    stale, stale_ctx = make_session(registry, who, idle=IDLE_TIMEOUT + timedelta(minutes=5))

    assert await registry.sweep() == 1
    assert stale_ctx.closed and not fresh_ctx.closed
    assert registry.count == 1
    assert fresh.id in registry._sessions
    assert stale.id not in registry._sessions


async def test_using_a_session_keeps_it_alive():
    registry = SessionRegistry()
    who = uuid.uuid4()
    session, _ = make_session(registry, who, idle=IDLE_TIMEOUT - timedelta(seconds=30))
    await registry.get(session.id, who)
    assert not session.expired
    assert await registry.sweep() == 0


async def test_shutdown_closes_everything():
    registry = SessionRegistry()
    who = uuid.uuid4()
    contexts = [make_session(registry, who)[1] for _ in range(3)]
    await registry.shutdown()
    assert all(c.closed for c in contexts)
    assert registry.count == 0
