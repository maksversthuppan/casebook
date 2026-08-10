"""Look at the real search page and report exactly what is on it.

    uv run python -m scripts.probe_portal                       # list districts
    uv run python -m scripts.probe_portal ERNAKULAM             # list courts there
    uv run python -m scripts.probe_portal ERNAKULAM "Munsiff Court, Ernakulam"

With a district and court it goes all the way to the search UI and dumps the
tabs, the inputs, the CAPTCHA element and any Server Action calls - which is
what the rest of the driver needs in order to be written against fact.

Run it from a network the portal will accept. It makes one page load and a few
clicks; do not loop it.
"""

import argparse
import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

from app.dcms.portal import (
    CASE_SEARCH_URL,
    COURT_PLACEHOLDER,
    DISTRICT_PLACEHOLDER,
    PortalError,
    list_options,
    open_search,
    select_court,
)
from app.dcms.session import USER_AGENT

SHOT = pathlib.Path("probe.png")


async def run(district: str | None, court: str | None, headed: bool) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        # The portal refuses connections outright to clients whose user agent
        # looks automated. This is not optional.
        page = await (
            await browser.new_context(
                viewport={"width": 1500, "height": 1100}, user_agent=USER_AGENT
            )
        ).new_page()

        actions: list[tuple[str, str]] = []
        page.on(
            "request",
            lambda r: actions.append((r.url, r.headers.get("next-action", "-")))
            if r.method == "POST"
            else None,
        )

        try:
            await open_search(page)
        except PortalError as exc:
            print(f"! {exc}")
            await browser.close()
            return 1

        print(f"loaded {CASE_SEARCH_URL}")
        print(f"title: {await page.title()}\n")

        if not district:
            print("districts:")
            for d in await list_options(page, DISTRICT_PLACEHOLDER):
                print("   ", d)
            print("\nPass one as the first argument to list its courts.")
            await browser.close()
            return 0

        if not court:
            from app.dcms.portal import _choose

            await _choose(page, DISTRICT_PLACEHOLDER, district)
            print(f"courts in {district}:")
            for c in await list_options(page, COURT_PLACEHOLDER):
                print("   ", c)
            print("\nPass one as the second argument to reach the search UI.")
            await browser.close()
            return 0

        state_l, district_l, court_l = await select_court(page, district, court)
        print("chosen, verbatim from the portal:")
        print(f"   state:         {state_l!r}")
        print(f"   district:      {district_l!r}")
        print(f"   establishment: {court_l!r}")
        print("   ^ these are what get recorded onto the Court\n")

        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(SHOT), full_page=True)
        print(f"screenshot: {SHOT.resolve()}\n")

        print("--- tabs / buttons now present ---")
        for el in await page.query_selector_all("[role=tab], button"):
            text = (await el.inner_text()).strip().replace("\n", " ")
            if text and len(text) < 30:
                print(
                    "   %-22r role=%-5s id=%r"
                    % (text, await el.get_attribute("role"), await el.get_attribute("id"))
                )

        print("\n--- inputs now present ---")
        for el in await page.query_selector_all("input"):
            ident = await el.get_attribute("id") or ""
            if "goog" in ident:
                continue
            print(
                "   placeholder=%-24r name=%r type=%r"
                % (
                    await el.get_attribute("placeholder"),
                    await el.get_attribute("name"),
                    await el.get_attribute("type"),
                )
            )

        print("\n--- images: the CAPTCHA should be among these ---")
        for el in await page.query_selector_all("img, canvas"):
            src = await el.get_attribute("src") or ""
            if "headerlogo" in src or "gstatic" in src:
                continue
            tag = await el.evaluate("e => e.tagName")
            print(f"   <{tag}> alt={await el.get_attribute('alt')!r}")
            print(f"        src={src[:160]!r}")
            print(f"        is a data: URI? {src.startswith('data:')}")

        print("\n--- POSTs seen (Server Actions carry a next-action header) ---")
        for url, action in actions or [("(none)", "-")]:
            print(f"   {url}\n      next-action={action}")

        await browser.close()
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("district", nargs="?")
    parser.add_argument("court", nargs="?")
    parser.add_argument("--headed", action="store_true", help="show the browser")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.district, args.court, args.headed)))


if __name__ == "__main__":
    main()
