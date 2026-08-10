"""Find out where the portal's fuller case-details content actually comes from.

A user-pasted "Case Details" view (Acts & Section, Crime Details, a full
hearing-history timeline with a presiding officer per entry, multiple
advocates per party) carries far more than the search response `extract_case`
reads today. That response has been captured for this exact case
(`tests/fixtures/dcms_case_found.txt`) and, checked directly, contains none of
it - no FIR/crime/officer/acts/section/history keys or substrings at all.

So either the page fires a follow-up request once a single case is found, or
the search response streams in more chunks over time than our one
`response.text()` call sees. This script drives one CNR search for a case
known to have that fuller content, and instead of taking only the search
POST's response, logs *every* response the page receives for a window after
submission - so the extra content's actual source can be read off directly.

Same rules as `probe_portal.py`: one CAPTCHA, solved by a person, never
automated (ADR-0003). The CAPTCHA is written to a file for the operator to
open and read themselves - this script never inspects that image.

    uv run python -m scripts.probe_case_detail \\
        THIRUVANANTHAPURAM "Addl. Chief Judicial Magistrate Court, Thiruvananthapuram" \\
        KLTV080027432025

Solve the CAPTCHA it writes to `probe_captcha.svg`, then create
`probe_captcha_code.txt` next to it (one line, the code) - the script polls
for that file. Output lands under `probe_capture/`: one file per response
seen, plus `probe_capture/index.txt` summarising method/url/status/type for
all of them.
"""

import argparse
import asyncio
import base64
import pathlib
import re
import sys
import time

from playwright.async_api import async_playwright

from app.dcms.portal import (
    PortalError,
    captcha_image,
    fill_identifier,
    open_search,
    select_court,
    select_tab,
)
from app.dcms.session import USER_AGENT
from app.models.enums import SearchMode

CAPTCHA_FILE = pathlib.Path("probe_captcha.svg")
CODE_FILE = pathlib.Path("probe_captcha_code.txt")
CAPTURE_DIR = pathlib.Path("probe_capture")

#: How long to keep recording responses after the Search click, so a follow-up
#: request has time to show up. The portal itself has no reason to be slow;
#: this is generous on purpose.
CAPTURE_WINDOW_SECONDS = 12
#: How long to wait for the operator to solve the CAPTCHA before giving up.
CODE_WAIT_TIMEOUT_SECONDS = 300

_DATA_URI = re.compile(r"^data:([^;]+);base64,(.*)$", re.DOTALL)


def _safe_name(url: str, index: int) -> str:
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("?", 1)[0])[-80:]
    return f"{index:03d}_{tail}"


async def _wait_for_code() -> str:
    print(f"\nCAPTCHA written to {CAPTCHA_FILE.resolve()}")
    print(f"Open it, read the code, then write it to {CODE_FILE.resolve()} (one line).")
    print(f"Waiting up to {CODE_WAIT_TIMEOUT_SECONDS}s...")
    deadline = time.monotonic() + CODE_WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if CODE_FILE.exists():
            code = CODE_FILE.read_text().strip()
            if code:
                return code
        await asyncio.sleep(2)
    raise PortalError("Timed out waiting for the CAPTCHA code.")


async def run(district: str, court: str, cnr: str) -> int:
    CAPTURE_DIR.mkdir(exist_ok=True)
    CAPTCHA_FILE.unlink(missing_ok=True)
    CODE_FILE.unlink(missing_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (
            await browser.new_context(
                viewport={"width": 1500, "height": 1100}, user_agent=USER_AGENT
            )
        ).new_page()

        seen: list[tuple[str, str, int, str]] = []
        counter = {"n": 0}

        def on_response(response):
            counter["n"] += 1
            index = counter["n"]
            seen.append(
                (response.request.method, response.url, response.status,
                 response.headers.get("content-type", ""))
            )

            async def _save():
                try:
                    body = await response.body()
                except Exception:  # noqa: BLE001 - best effort, some responses have no body
                    return
                path = CAPTURE_DIR / _safe_name(response.url, index)
                path.write_bytes(body)

            asyncio.ensure_future(_save())

        page.on("response", on_response)

        try:
            await open_search(page)
            await select_court(page, district, court)
            await select_tab(page, SearchMode.cnr)
            await fill_identifier(page, SearchMode.cnr, cnr)

            src = await captcha_image(page)
            match = _DATA_URI.match(src)
            if not match:
                raise PortalError("CAPTCHA was not a data: URI as expected.")
            mime, b64 = match.groups()
            ext = "svg" if "svg" in mime else "png"
            captcha_path = CAPTCHA_FILE.with_suffix(f".{ext}")
            captcha_path.write_bytes(base64.b64decode(b64))
            globals()["CAPTCHA_FILE"] = captcha_path  # so the printed path is right below

            code = await _wait_for_code()

            await page.get_by_placeholder("Enter captcha").fill(code)
            await page.get_by_role("button", name="Search", exact=True).click()
            print(f"submitted; recording every response for {CAPTURE_WINDOW_SECONDS}s...")
            await page.wait_for_timeout(CAPTURE_WINDOW_SECONDS * 1000)

            html_path = CAPTURE_DIR / "rendered_page.html"
            html_path.write_text(await page.content())

        except PortalError as exc:
            print(f"! {exc}")
            await browser.close()
            return 1
        finally:
            page.remove_listener("response", on_response)

        index_path = CAPTURE_DIR / "index.txt"
        with index_path.open("w") as f:
            for method, url, status, ctype in seen:
                f.write(f"{method:5} {status} {ctype:40} {url}\n")

        print(f"\n{len(seen)} responses captured under {CAPTURE_DIR.resolve()}")
        print(f"see {index_path.resolve()} for the summary")

        await browser.close()
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("district")
    parser.add_argument("court")
    parser.add_argument("cnr")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.district, args.court, args.cnr)))


if __name__ == "__main__":
    main()
