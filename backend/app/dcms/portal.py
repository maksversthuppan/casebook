"""Driving https://filing.keralacourts.in/caseSearch as a normal user would.

What is verified against the live page (2026-08-06) and what is not is marked
below. Nothing here reads, guesses or bypasses the CAPTCHA - a person solves it
every time (ADR-0003).
"""

import logging
import re

from playwright.async_api import Page

from app.models.enums import SearchMode

log = logging.getLogger(__name__)

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Collapse internal whitespace runs the way a browser renders them.

    A live case (2026-09-12): selecting a court option raised "did not take"
    even though the option text and the field's read-back value looked
    identical once displayed. `.strip()` only trims the ends - it doesn't
    catch the portal's own markup and the input's value disagreeing on
    *internal* whitespace (e.g. a doubled space), which HTML rendering
    collapses to one space for display either way, hiding the difference
    from whoever is looking at the page (or reading our error message
    rendered as HTML) even though a plain `==` still sees it.
    """
    return _WHITESPACE_RUN.sub(" ", text)

CASE_SEARCH_URL = "https://filing.keralacourts.in/caseSearch"

# The three cascading selectors are Mantine widgets: an <input> plus a hidden
# input, not a native <select>. They must be clicked open and an option picked.
# Their ids are regenerated on every render, so the stable handle is the
# placeholder text. VERIFIED against the live page.
STATE_PLACEHOLDER = "Select State"
DISTRICT_PLACEHOLDER = "Select District"
COURT_PLACEHOLDER = "Select Court"

DEFAULT_STATE = "KERALA"

#: Grace period after the inputs appear, before React has wired them up. Without
#: it the first click is silently lost and the dropdown never opens.
HYDRATION_SETTLE_MS = 1_500


class PortalError(Exception):
    """The portal could not be driven to where we needed it."""


async def open_search(page: Page, timeout: int = 45_000) -> None:
    """Load the search page and wait for it to hydrate."""
    try:
        response = await page.goto(
            CASE_SEARCH_URL, wait_until="domcontentloaded", timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the advocate as prose
        # The advocate gets a plain sentence; the real Playwright error (DNS,
        # connection reset, TLS failure, plain timeout) only exists here.
        log.warning("could not navigate to the DCMS portal: %r", exc)
        raise PortalError(
            "Could not reach the DCMS portal. It is often briefly unavailable; "
            "try again in a few minutes."
        ) from exc

    if response is not None and response.status >= 400:
        raise PortalError(f"The DCMS portal answered with {response.status}.")

    # The selectors only exist once React has hydrated. Being visible is not
    # enough: for a short while afterwards the inputs are painted but their
    # handlers are not attached, and a click on one is simply swallowed.
    try:
        await page.get_by_placeholder(STATE_PLACEHOLDER).wait_for(
            state="visible", timeout=20_000
        )
        await page.get_by_placeholder(DISTRICT_PLACEHOLDER).wait_for(
            state="visible", timeout=10_000
        )
    except Exception as exc:  # noqa: BLE001
        raise PortalError(
            "The DCMS search page loaded but did not finish rendering."
        ) from exc

    await page.wait_for_timeout(HYDRATION_SETTLE_MS)


async def _open_dropdown(page: Page, placeholder: str):
    """Click a Mantine select open and return a locator for *its* option list.

    All three dropdowns sit in the DOM at once, each as a Popover holding a
    `[role=listbox]`. Only the open one is visible, so the options must be scoped
    to the visible listbox - reading `[role=option]` off the page would mix
    districts in with states.
    """
    box = page.get_by_placeholder(placeholder)
    listbox = page.locator("[role=listbox]:visible")

    # One retry: a click landing a moment too early is swallowed rather than
    # erroring, and the page gives no signal that it happened.
    for attempt in (1, 2):
        await box.click()
        try:
            await listbox.first.wait_for(state="visible", timeout=5_000)
            return listbox.first
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise PortalError(f"The {placeholder!r} list did not open.") from None
            log.debug("%r did not open on the first click; retrying", placeholder)
            await page.wait_for_timeout(1_000)

    raise PortalError(f"The {placeholder!r} list did not open.")


async def _choose(page: Page, placeholder: str, wanted: str) -> str:
    """Open one Mantine select and pick an option.

    Returns the label actually chosen, which is what gets recorded onto the
    Court - it must match the portal's own wording exactly or a later refresh
    will not be able to re-select it.
    """
    box = page.get_by_placeholder(placeholder)
    listbox = await _open_dropdown(page, placeholder)
    elements = await listbox.get_by_role("option").all()
    labels = [(await o.inner_text()).strip() for o in elements]
    if not labels:
        raise PortalError(f"The portal offered no choices for {placeholder!r}.")

    index = next((i for i, label in enumerate(labels) if label == wanted.strip()), None)
    if index is None:
        index = next(
            (i for i, label in enumerate(labels) if wanted.lower() in label.lower()), None
        )
    if index is None:
        raise PortalError(
            f"{wanted!r} is not one of the choices the portal offers for "
            f"{placeholder!r}. It offers: {', '.join(labels[:12])}"
            + (" …" if len(labels) > 12 else "")
        )
    match = labels[index]

    # Click the exact element found above, not a re-query by text - Playwright's
    # `has_text` filter matches on substring, so "MC" also matches "Crl.MC" and
    # a `.first` pick can land on the wrong option whenever one label contains
    # another (real case: Thiruvananthapuram's "Choose Case Type" offers both).
    await elements[index].click()
    await page.wait_for_timeout(900)

    # The click on a Mantine option can land a moment too early and be
    # swallowed the same way the initial dropdown click can (see
    # `_open_dropdown`). Reading the input back catches that silently rather
    # than submitting a search the portal will treat as a different, blank
    # field.
    actual = (await box.input_value()).strip()
    if _normalize_ws(actual) != _normalize_ws(match):
        raise PortalError(
            f"Selecting {match!r} for {placeholder!r} did not take - the "
            f"field reads {actual!r} instead."
        )
    return match


async def list_options(page: Page, placeholder: str) -> list[str]:
    """What the portal currently offers for one selector, so an advocate can pick.

    Used by the ingestion wizard: the district and court lists come from the
    portal itself rather than from anything we maintain.
    """
    listbox = await _open_dropdown(page, placeholder)
    labels = [(await o.inner_text()).strip() for o in await listbox.get_by_role("option").all()]
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)
    return labels


async def select_court(
    page: Page, district: str, court: str, state: str = DEFAULT_STATE
) -> tuple[str, str, str]:
    """Drive State -> District -> Court, returning the labels actually chosen.

    Until this has been done the portal shows "Select state, district, and court
    to begin searching" and the search tabs are not in the DOM at all - which is
    why every search, CNR included, needs a court first (ADR-0004).
    """
    chosen_state = state
    # State comes pre-filled with KERALA; only touch it if it is something else.
    if state.upper() != DEFAULT_STATE:
        chosen_state = await _choose(page, STATE_PLACEHOLDER, state)

    chosen_district = await _choose(page, DISTRICT_PLACEHOLDER, district)
    chosen_court = await _choose(page, COURT_PLACEHOLDER, court)

    log.info("portal at %s / %s / %s", chosen_state, chosen_district, chosen_court)
    return chosen_state, chosen_district, chosen_court


# ---------------------------------------------------------------------------
# The search itself. All selectors below were read off the live page.
# ---------------------------------------------------------------------------

#: Tabs carry role="tab" and a stable accessible name. Their ids are of the form
#: `mantine-<random>-tab-cnr`, so the name is the stable handle, not the id.
TAB_FOR_MODE = {
    SearchMode.cnr: "CNR",
    SearchMode.case_number: "Case No",
    SearchMode.filing_number: "Filing No",
}

#: Which inputs each tab shows. VERIFIED.
IDENTIFIER_PLACEHOLDER = {
    SearchMode.cnr: "CNR Number",
    SearchMode.case_number: "Case Number",
    SearchMode.filing_number: "Filing Number",
}

CASE_TYPE_PLACEHOLDER = "Choose Case Type"
YEAR_PLACEHOLDER = "Year"
CAPTCHA_PLACEHOLDER = "Enter captcha"
CAPTCHA_IMAGE = "img[alt=Captcha]"


async def select_tab(page: Page, mode: SearchMode) -> None:
    """Choose which identifier is being searched by."""
    name = TAB_FOR_MODE[mode]
    try:
        await page.get_by_role("tab", name=name, exact=True).click()
        await page.get_by_placeholder(IDENTIFIER_PLACEHOLDER[mode]).wait_for(
            state="visible", timeout=10_000
        )
    except Exception as exc:  # noqa: BLE001
        raise PortalError(f"Could not open the {name!r} search on the portal.") from exc


async def fill_identifier(
    page: Page,
    mode: SearchMode,
    value: str,
    *,
    case_type: str | None = None,
    year: str | None = None,
) -> None:
    """Fill in whatever the chosen tab asks for.

    `CNR` wants one field. `Case No` and `Filing No` also want a case type and a
    year, which is why refresh prefers CNR once a Case has its CINO.

    A missing case type or year for those two tabs is refused rather than
    silently skipped - the portal treats an incomplete search as its own query
    and answers "not found" rather than erroring, which previously produced a
    Snapshot for the wrong search with no indication anything was left out.
    """
    if mode is not SearchMode.cnr:
        if not case_type:
            raise PortalError(f"{TAB_FOR_MODE[mode]!r} search needs a case type.")
        if not year:
            raise PortalError(f"{TAB_FOR_MODE[mode]!r} search needs a year.")
        await _choose(page, CASE_TYPE_PLACEHOLDER, case_type)
        await _fill_and_verify(page, YEAR_PLACEHOLDER, year)

    await _fill_and_verify(page, IDENTIFIER_PLACEHOLDER[mode], value)


async def _fill_and_verify(page: Page, placeholder: str, value: str) -> None:
    """Fill a plain input and read it back.

    `.fill()` on a field that is not yet wired up (same hydration window as the
    Mantine selects) can be silently swallowed, producing a search with a blank
    field and no error to say so.
    """
    field = page.get_by_placeholder(placeholder)
    await field.fill(value)
    actual = (await field.input_value()).strip()
    if actual != value.strip():
        raise PortalError(
            f"Typing into {placeholder!r} did not take - it reads {actual!r} "
            f"instead of {value!r}."
        )


async def case_types(page: Page) -> list[str]:
    """The case types this court offers, straight from the portal."""
    return await list_options(page, CASE_TYPE_PLACEHOLDER)


async def captcha_image(page: Page) -> str:
    """The CAPTCHA, as a `data:image/svg+xml;base64,...` URI.

    It is inlined in the DOM rather than served from a session-bound URL, so it
    can be handed straight to our own page - no fetching bytes back through the
    browser session. This is what ADR-0004 rested on.

    Read, shown to a person, and typed by that person. Never interpreted here.
    """
    img = page.locator(CAPTCHA_IMAGE)
    try:
        await img.wait_for(state="visible", timeout=10_000)
    except Exception as exc:  # noqa: BLE001
        raise PortalError("The portal did not show a CAPTCHA.") from exc

    src = await img.get_attribute("src")
    if not src:
        raise PortalError("The portal's CAPTCHA had no image.")
    return src


#: When a case is found, the page fires several more Server Action POSTs to the
#: same URL right after the first - case history, acts & section, crime
#: details, additional party/advocate rows, order metadata. Confirmed live
#: 2026-08-09 against a real case: ten such responses, all landing within a
#: few seconds of the click. `submit()` used to keep only the first and
#: discard the rest, silently - this window is what stops that.
FOLLOWUP_WINDOW_MS = 10_000


async def submit(page: Page, captcha_code: str, timeout: int = 45_000) -> list[str]:
    """Submit the search and capture every response that follows, in order.

    The search runs as a Next.js Server Action - a POST to the same URL carrying
    a `next-action` header - so the response is a Flight payload rather than a
    rendered page. But it is not the *only* POST to that URL: a found case's
    detail view is assembled from several more, fired automatically once the
    first resolves. All of them are captured whole and stored before anything
    is parsed out of them - a CAPTCHA was paid for the lot, not just the first.
    """
    await page.get_by_placeholder(CAPTCHA_PLACEHOLDER).fill(captcha_code)

    def is_search_post(response) -> bool:
        return (
            response.request.method == "POST"
            and CASE_SEARCH_URL.split("://", 1)[1] in response.url
        )

    responses: list[str] = []

    async def _collect(response) -> None:
        if not is_search_post(response):
            return
        try:
            responses.append(await response.text())
        except Exception:  # noqa: BLE001 - one unreadable body must not drop the rest
            log.warning("could not read a DCMS response body", exc_info=True)

    page.on("response", _collect)
    try:
        async with page.expect_response(is_search_post, timeout=timeout):
            await page.get_by_role("button", name="Search", exact=True).click()
        # The first response has landed; give the rest of the burst time to.
        await page.wait_for_timeout(FOLLOWUP_WINDOW_MS)
    except Exception as exc:  # noqa: BLE001
        raise PortalError(
            "The search did not come back. The CAPTCHA may have expired - "
            "the portal rotates it about every thirty seconds."
        ) from exc
    finally:
        page.remove_listener("response", _collect)

    return responses
