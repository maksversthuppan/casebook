"""TEMPORARY - remove after diagnosing the Render-can't-reach-the-portal issue.

`app/dcms/portal.py`'s `open_search` times out reaching the DCMS portal from
Render with no underlying network error, which is consistent with either a
blanket IP/ASN block or a TLS-fingerprint check on Chromium's handshake
specifically. Chromium can't tell those apart; a plain, non-browser TCP/TLS/
HTTP probe from the same network can, by seeing exactly which layer stalls.
See docs/hosting-plan.md, "Finding: the DCMS portal is unreachable from
Render entirely".
"""

import asyncio
import socket
import ssl
import time
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentAdvocate

router = APIRouter(prefix="/debug", tags=["debug"])

PORTAL_HOST = "filing.keralacourts.in"
PORTAL_PORT = 443
STAGE_TIMEOUT = 15


async def _stage(coro) -> dict[str, Any]:
    """Run one probe step, timed, with its result or its exception - never both
    raising past this point, since a later stage still needs a chance to run.
    """
    t0 = time.monotonic()
    try:
        value = await asyncio.wait_for(coro, timeout=STAGE_TIMEOUT)
        return {"ok": True, "seconds": round(time.monotonic() - t0, 2), "value": value}
    except Exception as exc:  # noqa: BLE001 - the exception itself is the point
        return {"ok": False, "seconds": round(time.monotonic() - t0, 2), "error": repr(exc)}


@router.get("/portal-probe")
async def portal_probe(_: CurrentAdvocate) -> dict:
    """DNS, then a plain TCP connect, then a TLS+HTTP request - each timed and
    reported separately, so a hang can be pinned to one layer instead of
    arriving as one opaque Playwright timeout.
    """
    result: dict[str, Any] = {"host": PORTAL_HOST}
    loop = asyncio.get_event_loop()

    dns = await _stage(loop.getaddrinfo(PORTAL_HOST, PORTAL_PORT, type=socket.SOCK_STREAM))
    if dns["ok"]:
        dns["addresses"] = sorted({addr[4][0] for addr in dns.pop("value")})
    result["dns"] = dns
    if not dns["ok"]:
        return result

    plain_writer: asyncio.StreamWriter | None = None

    async def _plain_connect() -> None:
        nonlocal plain_writer
        _, plain_writer = await asyncio.open_connection(PORTAL_HOST, PORTAL_PORT)

    tcp = await _stage(_plain_connect())
    tcp.pop("value", None)
    result["tcp_connect"] = tcp
    if plain_writer is not None:
        plain_writer.close()
    if not tcp["ok"]:
        return result

    tls_reader: asyncio.StreamReader | None = None
    tls_writer: asyncio.StreamWriter | None = None

    async def _tls_connect() -> None:
        nonlocal tls_reader, tls_writer
        ctx = ssl.create_default_context()
        tls_reader, tls_writer = await asyncio.open_connection(
            PORTAL_HOST, PORTAL_PORT, ssl=ctx, server_hostname=PORTAL_HOST
        )

    tls = await _stage(_tls_connect())
    tls.pop("value", None)
    result["tls_handshake"] = tls
    if not tls["ok"]:
        return result

    async def _http_get() -> str:
        request = (
            f"GET /caseSearch HTTP/1.1\r\n"
            f"Host: {PORTAL_HOST}\r\n"
            f"User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36\r\n"
            f"Connection: close\r\n\r\n"
        )
        tls_writer.write(request.encode())
        await tls_writer.drain()
        data = await tls_reader.read(2048)
        return data.split(b"\r\n", 1)[0].decode(errors="replace")

    http = await _stage(_http_get())
    if http["ok"]:
        http["status_line"] = http.pop("value")
    result["http_get"] = http
    tls_writer.close()

    return result
