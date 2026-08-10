"""Making sense of a Next.js Server Action response.

The search answers with an RSC Flight payload: numbered lines, each holding a
JSON value, e.g.

    0:{"a":"$@1"}
    1:[["$","div",null,{...}]]

`parse_flight` splits that into chunks. `extract_case` reads the one Case a
search describes out of those chunks, written against two real captures:

- `tests/fixtures/dcms_case_found.txt` - a CNR search that found a case
- `tests/fixtures/dcms_case_not_found.txt` - a Case No search with an
  incomplete case type (fixed since, see ROADMAP), which the portal answers
  with no error, just nothing to find
- `tests/fixtures/dcms_case_detail_burst.txt` - the same case as
  `dcms_case_found.txt`, but with the *other* nine responses the portal fires
  once it finds one: case history, acts & section, crime details, additional
  party/advocate rows, order metadata. `extract_case_detail` reads these; it
  classifies each response by the keys its rows carry rather than by
  position, since nothing guarantees the burst always lands in the same order

Every later Snapshot that turns up a shape these do not cover should add a
fixture and extend `extract_case`/`extract_case_detail` rather than being
special-cased silently.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any

from app.config import IST

#: The portal is Kerala-only; every date it returns is IST regardless of the
#: `Z` UTC suffix Flight serialises it with (see `_parse_portal_date`).
_IST = IST

LINE = re.compile(r"^([0-9a-f]+):(.*)$")

#: A found case's detail view is assembled from several Server Action responses,
#: not one - `portal.submit()` now returns all of them. They are joined into a
#: single string for `raw_response` (still one Text column, nothing re-encoded)
#: on a separator that cannot appear inside a Flight payload, which is why it is
#: an ASCII control character rather than anything printable.
RESPONSE_SEPARATOR = "\x1f"


def join_responses(responses: list[str]) -> str:
    """Combine every response from one submit() into what `raw_response` stores."""
    return RESPONSE_SEPARATOR.join(responses)


def split_responses(raw: str) -> list[str]:
    """The reverse of `join_responses`, for reading a stored Snapshot back apart."""
    return raw.split(RESPONSE_SEPARATOR)


def parse_flight(raw: str) -> dict[str, Any]:
    """Split a Flight payload into its numbered chunks, decoding what is JSON."""
    chunks: dict[str, Any] = {}
    undecoded: list[str] = []

    for line in raw.splitlines():
        match = LINE.match(line)
        if not match:
            if line.strip():
                undecoded.append(line[:400])
            continue

        key, body = match.groups()
        body = body.strip()
        if not body:
            continue
        try:
            chunks[key] = json.loads(body)
        except json.JSONDecodeError:
            chunks[key] = {"__raw__": body[:2000]}

    return {"chunks": chunks, "undecoded": undecoded}


def walk(value: Any, depth: int = 0):
    """Every (path, value) pair in a decoded payload, for hunting fields."""
    stack: list[tuple[str, Any]] = [("", value)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                stack.append((f"{path}.{k}", v))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                stack.append((f"{path}[{i}]", v))
        else:
            yield path, node


def find_like(parsed: dict[str, Any], *needles: str) -> dict[str, Any]:
    """Paths whose key or value mentions any of the needles.

    Used to locate the CINO, the party names and the hearing list inside a real
    payload the first time one is captured.
    """
    hits: dict[str, Any] = {}
    lowered = [n.lower() for n in needles]
    for path, value in walk(parsed):
        haystack = f"{path} {value}".lower()
        if any(n in haystack for n in lowered):
            hits[path] = value
    return hits


_CHUNK_REF = re.compile(r"^\$@(\w+)$")


def _resolve(chunks: dict[str, Any]) -> Any:
    """Follow chunk "0"'s promise reference to whichever chunk holds the payload.

    Chunk "0" is always of the shape `["$@<id>", [...]]` - Flight's way of
    saying "this resolves to chunk <id>". Resolving it rather than assuming
    <id> is always "1" survives a future payload that streams differently.

    The main search response resolves to a dict (`{"data": [...], ...}`); every
    one of the nine follow-up responses resolves to a plain list instead, empty
    or not - so this returns whatever it finds, and callers narrow the type.
    """
    root = chunks.get("0")
    if not isinstance(root, list) or not root or not isinstance(root[0], str):
        return None
    match = _CHUNK_REF.match(root[0])
    if not match:
        return None
    return chunks.get(match.group(1))


def _resolve_body(chunks: dict[str, Any]) -> dict[str, Any] | None:
    body = _resolve(chunks)
    return body if isinstance(body, dict) else None


def _resolve_rows(chunks: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _resolve(chunks)
    return rows if isinstance(rows, list) else []


def _parse_portal_date(value: Any) -> dt.date | None:
    """Decode one of the portal's `"$D<iso>"` dates into an IST calendar date.

    Every one observed so far carries a `T18:30:00.000Z` time - UTC midnight
    minus 5:30, i.e. IST midnight. Taking `.date()` of the raw UTC instant
    reads every date one day early; converting to IST first is required.
    """
    if not isinstance(value, str) or not value.startswith("$D"):
        return None
    try:
        moment = dt.datetime.fromisoformat(value[2:])
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(_IST).date()


@dataclass
class PortalParty:
    """One person on one side of a case, in the portal's own vocabulary.

    Deliberately not "client" or "opposite party" - CONTEXT.md is explicit that
    only a person can say which side is the firm's, so this stays as
    petitioner/respondent until the review screen asks.
    """

    name: str
    advocate_name: str | None
    advocate_registration: str | None
    #: 0 for the cause-title's lead party ("Rekha Devi P S and 2 Others" is
    #: still one name, one row) - the portal's own numbering for anyone
    #: enumerated separately in `adlData`. Ties this individual to their own
    #: Counsel entries in the burst (`PortalCaseDetail.counsel_for`).
    party_no: int = 0


@dataclass
class PortalCase:
    """What one search response says about one Case, read but not yet decided.

    `registration_number` and `filing_number` are the portal's own raw
    `case_no` / `filing_no` strings, not the "MC 58/2025" shorthand a lawyer
    would type to find it - the payload never states that shorthand outright,
    and `reg_no`/`fil_no` look encoded (e.g. `reg_no: 200058` for a search
    value of `58`) in a way not yet understood from one example. Treating the
    portal's own strings as the label avoids inventing a decoding scheme.

    `petitioner` / `respondent` is only ever the cause-title's lead name - the
    same string the portal's own detail page shows for row 1 ("Rekha Devi P S
    and 2 Others"), never decoded further. Anyone the "and N Others"/"and
    ANOTHER" is standing in for is `petitioner_others` / `respondent_others`
    instead - real individuals the portal enumerates separately in `adlData`,
    previously read by nothing here at all.
    """

    cino: str
    case_type: str | None
    registration_number: str | None
    registration_date: dt.date | None
    filing_number: str | None
    filing_date: dt.date | None
    court_status: str | None
    subject: str | None
    petitioner: PortalParty | None
    respondent: PortalParty | None
    petitioner_others: list[PortalParty]
    respondent_others: list[PortalParty]
    first_hearing: dt.date | None
    next_hearing: dt.date | None
    last_hearing: dt.date | None


def _party(row: dict[str, Any], prefix: str) -> PortalParty | None:
    name = row.get(f"{prefix}_name")
    if not name:
        return None
    return PortalParty(
        name=name,
        advocate_name=row.get(f"{prefix}_adv") or None,
        advocate_registration=row.get(f"{prefix}_adv_reg") or None,
    )


def _others(body: dict[str, Any], type_value: int) -> list[PortalParty]:
    """The individuals `adlData` enumerates for one side, in cause-title order.

    Only the ones "and N Others"/"and ANOTHER" stands in for - the lead name
    itself never appears here, only in the main row's `pet_name`/`res_name`.
    """
    rows = [
        r for r in (body.get("adlData") or []) if r.get("type") == type_value and r.get("name")
    ]
    rows.sort(key=lambda r: r.get("party_no", 0))
    return [
        PortalParty(
            name=row["name"],
            advocate_name=row.get("adv_name") or None,
            advocate_registration=row.get("adv_reg") or None,
            party_no=row.get("party_no", 0),
        )
        for row in rows
    ]


def extract_cases(parsed: dict[str, Any]) -> list[PortalCase]:
    """Every Case a search response describes, in the order the portal listed them.

    A search that matches nothing is not an error - the portal answers with a
    thin `{"status": "N"}` and no `data`, e.g. an incomplete Case No search
    (case type or year missing or wrong). That is indistinguishable here from
    a genuinely correct search for a case that does not exist, which is fine:
    both mean there is nothing to show, and this returns an empty list.

    A list rather than one Case because the Advocate Name tab returns every
    case an advocate is on in a court for a single CAPTCHA - the realistic way
    to load a backlog, and phase 2's bulk ingestion. Every step from here to a
    Case is written to take one element of this list, so that arriving needs no
    rewrite of the parser.

    `data` has been seen holding two near-identical rows for one case, differing
    only in a `type` field (1 vs 2) whose meaning is not yet known (see
    ROADMAP's open questions). They are deduplicated by CINO here, first row
    winning - the same assumption as before, now stated where it is made rather
    than hidden in a `rows[0]`.
    """
    body = _resolve_body(parsed.get("chunks", {}))
    if body is None:
        return []

    cases: list[PortalCase] = []
    seen: set[str] = set()
    for row in body.get("data") or []:
        cino = row.get("cino")
        if not cino or cino in seen:
            continue
        seen.add(cino)
        cases.append(_case_from_row(body, row))
    return cases


def extract_case(parsed: dict[str, Any]) -> PortalCase | None:
    """The one Case a search response describes, or `None` if it found none.

    The single-result form of `extract_cases`, for the searches that can only
    ever answer with one case - CNR, Case No, Filing No, which is every tab
    Ingestion and Refresh use today.
    """
    cases = extract_cases(parsed)
    return cases[0] if cases else None


def _case_from_row(body: dict[str, Any], row: dict[str, Any]) -> PortalCase:
    """One `data` row, read against the response body it came in.

    `body` is needed as well as `row` for the two things the portal keeps
    outside the row: the Court Status, and `adlData`'s enumeration of anyone
    the cause title's "and N Others" stands in for. Both are read per-body, so
    a multi-case payload would hand every case the same ones - correct for the
    one-result tabs, and to be revisited against a real Advocate Name capture,
    which is the only thing that can say how that payload keys them.
    """
    return PortalCase(
        cino=row["cino"],
        case_type=row.get("reg_name"),
        registration_number=row.get("case_no"),
        registration_date=_parse_portal_date(row.get("dt_regis")),
        filing_number=row.get("filing_no"),
        filing_date=_parse_portal_date(row.get("date_of_filing")),
        court_status=body.get("status"),
        subject=row.get("subject_name"),
        petitioner=_party(row, "pet"),
        respondent=_party(row, "res"),
        petitioner_others=_others(body, 1),
        respondent_others=_others(body, 2),
        first_hearing=_parse_portal_date(row.get("date_first_list")),
        next_hearing=_parse_portal_date(row.get("date_next_list")),
        last_hearing=_parse_portal_date(row.get("date_last_list")),
    )


# ---------------------------------------------------------------------------
# The other nine responses. See CONTEXT.md ("Crime Details", "Act & Section",
# "Counsel", "Presiding Officer") and ADR-0006 for why each of these is shaped
# the way it is.
# ---------------------------------------------------------------------------


@dataclass
class PortalCounsel:
    """One advocate the portal has on record for a side.

    Not the main response's single `pet_adv`/`res_adv` - this comes from the
    additional-party-rows response, which is where a side's *other* advocates
    turn up (real case: two, "AJITH R" and "ASHEER A K", for one respondent).
    """

    name: str
    registration: str | None


@dataclass
class PortalHearingRow:
    """One entry in a case's Case History timeline.

    `next_date` is what that entry adjourned to - normally another entry's own
    `date`, except on the most recent row, where it is the still-scheduled
    Hearing nothing else in the burst reports.
    """

    date: dt.date
    purpose: str | None
    outcome: str | None
    presiding_officer: str | None
    next_date: dt.date | None


@dataclass
class PortalActSection:
    code: str | None
    name: str
    section: str | None


@dataclass
class PortalCrimeDetails:
    cr_no: str | None
    fir_no: str | None
    fir_year: int | None
    fir_date: dt.date | None
    investigating_officer: str | None
    police_station: str | None
    rank: str | None


@dataclass
class PortalCaseDetail:
    """Everything the nine responses after the main search result carry.

    `counsel_by_party` is keyed by `(type, party_no)` - `type` 1 for the
    petitioner side, 2 for the respondent side, `party_no` 0 for the
    cause-title's lead party and the portal's own numbering for anyone
    `adlData` enumerates separately (`PortalParty.party_no`). Deduplicated by
    name within each key. Counsel is genuinely per individual, not per side -
    this response carries `party_no` for exactly that reason, confirmed
    against a real case (ROADMAP.md, 2026-08-09) where two individuals on the
    same side happened to share both their advocates, which is what made the
    earlier per-side approximation look right when it was actually coarser
    than the data.

    `order_dates` is deliberately just dates, not full order metadata (doc
    name, order number) - that is Phase 2 (documents); this is only enough to
    mark a Hearing's `order_available`.

    `kinds_seen` is which of the five shapes actually turned up in the burst,
    which is not the same question as what was found in them. A Snapshot whose
    burst never arrived reports no acts and no crime details in exactly the
    same way as one whose case genuinely has none - and applying the first over
    a Case would wipe what an earlier Refresh correctly recorded. Every
    wholesale replacement is gated on this rather than on emptiness (ADR-0007).
    """

    hearings: list[PortalHearingRow]
    act_sections: list[PortalActSection]
    crime_details: PortalCrimeDetails | None
    counsel_by_party: dict[tuple[int, int], list[PortalCounsel]]
    order_dates: list[dt.date]
    kinds_seen: frozenset[str] = frozenset()

    def counsel_for(self, type_value: int, party_no: int) -> list[PortalCounsel]:
        return self.counsel_by_party.get((type_value, party_no), [])

    def reported(self, kind: str) -> bool:
        """Did the burst carry a response of this shape at all?"""
        return kind in self.kinds_seen


def _classify_rows(rows: list[dict[str, Any]]) -> str | None:
    """Which of the nine responses this is, by the keys its first row carries.

    Classified by shape rather than position: the burst has so far always
    landed in the same order, but nothing guarantees it, and an empty response
    (seen for categories a given case has none of) carries no keys to classify
    by anyway.

    That last point has a consequence worth stating: an empty response is
    indistinguishable from a response that never came, so it never lands in
    `PortalCaseDetail.kinds_seen` and a Refresh will not clear that block. The
    error is in the safe direction - a Case keeps an Act & Section the court has
    stopped reporting, rather than losing one the portal simply did not repeat.
    Reachable only by a real capture where a case's acts genuinely disappear;
    fix it then, against evidence, rather than by guessing at burst order now.
    """
    if not rows:
        return None
    keys = set(rows[0].keys())
    if {"purpose_name", "order_remark", "names"} <= keys:
        return "hearings"
    if {"acts", "actname", "section"} <= keys:
        return "acts"
    if {"crno", "fir_no", "police_st_name"} <= keys:
        return "crime"
    if {"adv_name", "pet_res", "type"} <= keys:
        return "counsel"
    if {"doc_type", "docu_name"} <= keys:
        return "orders"
    return "unknown"


def extract_case_detail(responses: list[str]) -> PortalCaseDetail:
    """Everything the responses *after* the main search result carry.

    Called with `responses[1:]` from a `submit()` capture (or a stored
    Snapshot's `raw_response`, split back apart) - `responses[0]` is the main
    search result `extract_case` already reads.
    """
    hearings: list[PortalHearingRow] = []
    act_sections: list[PortalActSection] = []
    crime_details: PortalCrimeDetails | None = None
    counsel_by_party: dict[tuple[int, int], dict[str, PortalCounsel]] = {}
    order_dates: list[dt.date] = []
    kinds_seen: set[str] = set()

    for raw in responses:
        rows = _resolve_rows(parse_flight(raw).get("chunks", {}))
        kind = _classify_rows(rows)
        if kind is not None and kind != "unknown":
            kinds_seen.add(kind)

        if kind == "hearings":
            for row in rows:
                date = _parse_portal_date(row.get("todays_date"))
                if date is None:
                    continue
                hearings.append(
                    PortalHearingRow(
                        date=date,
                        purpose=row.get("purpose_name") or None,
                        outcome=row.get("order_remark") or None,
                        presiding_officer=row.get("names") or None,
                        next_date=_parse_portal_date(row.get("next_date")),
                    )
                )
        elif kind == "acts":
            for row in rows:
                name = row.get("actname")
                if not name:
                    continue
                act_sections.append(
                    PortalActSection(
                        code=row.get("acts") or None,
                        name=name,
                        section=row.get("section") or None,
                    )
                )
        elif kind == "crime":
            row = rows[0]
            # The portal returns this row even for cases with no real crime
            # data - most of it null (see this case: only police_st_name is
            # set). A row with nothing at all in it is not worth keeping.
            if any(
                row.get(key)
                for key in ("crno", "fir_no", "fir_date", "investofficer", "police_st_name", "rank")
            ):
                crime_details = PortalCrimeDetails(
                    cr_no=row.get("crno") or None,
                    fir_no=row.get("fir_no") or None,
                    fir_year=row.get("fir_year") or None,
                    fir_date=_parse_portal_date(row.get("fir_date")),
                    investigating_officer=row.get("investofficer") or None,
                    police_station=row.get("police_st_name") or None,
                    rank=row.get("rank") or None,
                )
        elif kind == "counsel":
            for row in rows:
                name = row.get("adv_name")
                if not name:
                    continue
                counsel = PortalCounsel(
                    name=" ".join(name.split()), registration=row.get("adv_reg") or None
                )
                # 1 = petitioner side, 2 = respondent side - confirmed against
                # both this response and the main response's `adlData` rows for
                # the same case (ROADMAP.md, 2026-08-09).
                key = (row.get("type"), row.get("party_no", 0))
                counsel_by_party.setdefault(key, {}).setdefault(counsel.name, counsel)
        elif kind == "orders":
            for row in rows:
                order_date = _parse_portal_date(row.get("order_dt"))
                if order_date is not None:
                    order_dates.append(order_date)

    return PortalCaseDetail(
        hearings=sorted(hearings, key=lambda h: h.date),
        act_sections=act_sections,
        crime_details=crime_details,
        counsel_by_party={key: list(names.values()) for key, names in counsel_by_party.items()},
        order_dates=order_dates,
        kinds_seen=frozenset(kinds_seen),
    )
