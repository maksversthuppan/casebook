# Roadmap

The execution plan for the case repository. Read alongside `CONTEXT.md` (the
vocabulary) and `docs/adr/` (the decisions and why). **Where this file and those
disagree, they win** — a disagreement is a bug in this file.

Tick items as they land, and add a line under *Findings* when reality contradicts
an assumption. This file is the memory between sessions; keep it honest rather
than tidy.

**Status: phase 1 is complete — 1a, 1b, 1c, 1d and 1e.** Cases, parties, courts, advocates,
hearings, diary entries, notes and the timeline all work, and so does the whole
DCMS round trip — Ingestion and Refresh. The firm's own facts about a Case — its
Vakalath, its Firm Status and how it got there, and how to reach a client — work
too. Tasks, the dashboard and the search box landed last. 161 tests passing.

Phase 1c was built after 1d and 1e rather than before them, because Ingestion
from DCMS is the feature the firm actually wants and nothing in 1c blocked it —
hearings already existed to receive the history a Snapshot returns, which was
the only real dependency. The build order below is kept in its original
numbering so the ADRs still read correctly; only the order of work changed.

**Phase 1d, as of 2026-08-10: complete.** Ingestion and Refresh both work end
to end. A Case is found on the portal, reviewed and created; a later Snapshot is
captured against it, diffed field by field and Hearing by Hearing, and applied
whole or discarded and kept.

Not yet done, and deliberately: a Case with no CINO cannot be refreshed, because
a Refresh searches by CNR and the portal's raw `case_no` is not the shorthand its
own Case No tab wants (see the open question on `reg_no`'s encoding). The screen
says so rather than offering a button that cannot work.

---

## Rules that must not be broken

These are the load-bearing invariants. Everything else is negotiable.

1. **A refresh replaces every court-sourced fact, and touches nothing else.**
   Court Status, Hearings, the court's own labels, Act & Section, Crime Details
   and Counsel are the court's account and are replaced wholesale. Never a Diary
   Entry, Internal Note, Task, Firm Status, tag, a Hearing's Representation, or a
   Party the firm has linked. Enforce this at the data-access layer, not by
   convention. (ADR-0002, restated in full by ADR-0007)
2. **A snapshot is applied whole or discarded whole.** No per-field selection,
   ever — a Case must never hold a mixture of portal data and human correction.
3. **Every snapshot is stored the moment it arrives**, before parsing, and kept
   afterwards whether applied or rejected. An advocate paid a CAPTCHA for it.
4. **The CAPTCHA is always solved by a person.** No reading, guessing, bypassing
   or automating it, and no scheduled or bulk fetching of any kind. (ADR-0003)
5. **The next hearing date is derived** from the earliest scheduled Hearing and
   is never stored on the Case.
6. **Lists and dashboards filter on Firm Status, never Court Status.** The two
   legitimately disagree. (ADR-0002)
7. **Case identity is internal.** CINO is unique when present but nullable;
   filing and registration numbers are mutable labels, never identity.

---

## Phase 1a — Foundations ✔

No DCMS involvement. Cases are created by hand only; ingestion arrives in 1d.

- [x] Project scaffold: FastAPI, PostgreSQL (Docker), Next.js 16, Alembic
- [x] Session-based auth, login, `advocates` seeded via `scripts/seed.py`
- [x] `parties`, and `case_parties` linking a Party to a Case with a role
      (`client` / `opposite_party`), a display order, and the portal's raw party
      string kept beside the link
- [x] `courts` — name, portal state / district / establishment (nullable), with
      provisional-versus-complete derived from whether those are set. Partial
      unique index on portal district + establishment, so provisional courts are
      exempt and only complete ones must be distinct
- [x] `cases` — internal id, nullable-unique `cino`, `filing_number`,
      `registration_number`, `case_type`, `court_id`, `court_status`,
      `firm_status`, `last_refreshed_at`
- [x] `assignments` with role (`lead` / `assisting` / `appearing`)
- [x] `case_relations` — directional, typed (`appeal_of`, `execution_of`,
      `connected_to`), created by hand
- [x] `tags`, `case_tags`
- [x] Manual case creation requiring **only** a court, one client Party, and one
      Advocate with a role. A court may be added inline as provisional
- [x] Case page shell: header, parties, advocates, both statuses

Table names are plural throughout, because `case` is a reserved SQL keyword and
quoting it in every hand-written query is a papercut not worth having.

`CaseUpdate` sets `extra="forbid"`, so an attempt to write `court_status` or
`cino` by hand is refused with a 422 rather than silently dropped. Three tests in
`tests/test_cases.py::TestOwnership` hold that line.

## Phase 1b — The record over time ✔

The dashboard depends on this working *without* DCMS, which is why advocates can
record Hearings themselves.

- [x] `hearings` — date, `state` (`scheduled` / `held` / `superseded` /
      `unrecorded`), `source` (`firm` / `court`), purpose, outcome,
      `order_available`. Unique on (case, date)
- [x] Advocates can record and amend a firm-sourced Hearing, typically the next
      date announced in court. A **court-sourced Hearing is refused** for edit
      and delete with a 409 — it changes only by applying a newer Snapshot
- [x] Case next hearing date **derived** via a correlated `column_property` over
      the earliest scheduled Hearing. Never stored, so it cannot drift.
      Deliberately not filtered to future dates: a scheduled date that has passed
      is surfaced, in amber, rather than hidden
- [x] `diary_entries` — date of record, author, body. Only the author may amend
      or delete their own, so nothing is silently misattributed
- [x] `internal_notes` — case-level, no date of record, absent from the timeline
- [x] Timeline: Hearings and Diary Entries interleaved by date, newest first,
      source visible; on a shared date the court's account reads above the note

`hearings` is unique on (case, date) because a case has one posting per date.
That is what will make the phase-1d takeover rule unambiguous — a Snapshot
reporting on a date knows exactly which Hearing it supersedes.

`tests/test_record.py::TestRefreshBoundary` fixes the ADR-0002 boundary now, by
writing the court-owned fields directly and asserting authored text survives
verbatim. Phase 1d has something to violate.

## Phase 1c — Working views ✔

- [x] `tasks` — case, assignee, title, optional originating diary entry, and a
      deadline that is either a fixed date **or** due-before-the-next-hearing,
      enforced by `ck_task_one_kind_of_deadline` *and* by clearing the other
      whenever one is set, so two separate edits cannot reach the state one edit
      is refused for. Neither is allowed too: work is often owed with no date.
      `done` is a nullable `done_at` plus `done_by` rather than a boolean —
      "when" gets asked as often as "whether". Anyone may tick anyone's off;
      who did is recorded, as everywhere else
- [x] `diary_entry_id` is **`ON DELETE SET NULL`**, which is the whole of
      CONTEXT.md's "it is the Case's, not the entry's" expressed in DDL:
      deleting the day's note drops the link and keeps the obligation
- [x] Due-before-next-hearing resolves at read time as a `column_property`
      (`Task.due_on`), not in Python — so "everything due this week" stays one
      ordered query and a moving deadline sorts alongside a fixed one. Null
      means no deadline *or* no scheduled Hearing yet to be due before, which
      the UI distinguishes in words
- [x] Home dashboard at `/` (was a redirect to `/cases`): hearings in the next
      seven days, scheduled dates that passed with nothing recorded against
      them, tasks owed soonest-first, and cases unconfirmed with DCMS for over
      30 days. "Mine" throughout means a Case the advocate holds an *Assignment*
      on — the standing roster, not one Hearing's Representation. Relinquished
      and closed Cases are absent: this is a view of work in hand
- [x] Single search box — `GET /search`. Substring on CINO, both court numbers
      and case type; substring on Party names; Postgres full-text over diary
      entries and notes. Every result says **why** it matched, with the hit
      marked in a `ts_headline` snippet, and a case matching several ways keeps
      every reason. Identifier hits rank above party hits above prose. The
      `/cases` box switches to it whenever there is a term, keeping the status
      and Mine filters. No filter builder

## Phase 1d — DCMS ✔  *(brought forward ahead of 1c)*

Order within this phase matters; do not reorder.

- [x] **De-risk first.** ADR-0004 holds. The CAPTCHA is an inline
      `data:image/svg+xml;base64` URI on `img[alt=Captcha]`, so it is read off the
      DOM and handed to our page directly — no session-bound fetch needed. The
      server-side-browser topology stands
- [x] Refresh sessions: one live Playwright context per in-flight operation, held
      in an in-memory registry keyed by session id, closed on success, failure,
      abandonment or timeout. Idle deadline of 10 minutes with a background
      sweeper; a session belongs to one advocate and cannot be taken over; the
      browser starts lazily and is closed in the app lifespan.
      `app/dcms/{browser,session}.py`, `tests/test_portal_sessions.py`
- [x] Portal driver — `app/dcms/portal.py`. Open the search page and wait out
      hydration; drive State → District → Court returning the labels *verbatim*;
      select the `CNR` / `Case No` / `Filing No` tab; fill the identifier (plus
      case type and year where the tab asks); read the CAPTCHA; submit and
      capture **every** Server Action response a found case triggers, not just
      the first (see Findings, 2026-08-09 — this was the one real correction
      `submit()` needed once actually run against a live CAPTCHA). Every
      selector was read off the live page and verified against it, `submit()`
      included
- [x] `dcms_snapshots` — nullable `case_id` (during ingestion the snapshot exists
      before the Case), `court_id`, search mode and value, raw response, parsed
      payload, `parse_error`, `fetched_at`/`fetched_by`, `status` (`captured` /
      `applied` / `rejected` / `superseded`), `decided_at`/`decided_by`

`scripts/probe_portal.py` re-dumps the live page whenever the portal changes
under us:

```bash
cd backend
uv run python -m scripts.probe_portal                      # list districts
uv run python -m scripts.probe_portal ERNAKULAM            # list its courts
uv run python -m scripts.probe_portal ERNAKULAM "<court>"  # reach the search UI
```

It makes one page load and a few clicks. Do not loop it.

- [x] Parser — `app/dcms/flight.py`. The response **is** a Server Action Flight
      payload. `parse_flight` splits it into numbered chunks; `extract_case`
      resolves chunk `0`'s promise reference and reads CINO, case type, Court
      Status, subject, both parties (name, advocate, advocate registration) and
      the three hearing dates the payload carries, converting them from the
      portal's UTC-midnight encoding to IST (see Findings, 2026-08-09).
      Tested against two real captures under `tests/fixtures/`
      (`tests/test_flight.py`) — one found case, one that matched nothing.
      `registration_number` / `filing_number` are the portal's own raw
      `case_no` / `filing_no` strings, not the "MC 58/2025" shorthand a lawyer
      types to search — `reg_no`/`fil_no`'s numeric encoding (`58` becomes
      `200058`) isn't understood well enough from one example to decode into
      that shorthand. `find_like()` stays for widening the mapping as more
      payload shapes turn up
- [x] **Ingestion wizard** (ADR-0005) — `app/api/ingest.py`, `app/ingest/page.tsx`.
      Open a session, list districts and courts from the portal itself, select a
      court and read its case types, choose the CNR / Case No / Filing No tab,
      fill the identifier, show the CAPTCHA to the advocate, submit, and store
      the Snapshot before parsing. A found Case flows straight into the review
      step below; a "not found" result shows the raw payload instead, same as a
      parse failure. Leaving the page cancels the session so no browser is
      stranded
- [x] Duplicate guard — a CNR already held is caught at the identifier step,
      **before** the advocate spends a CAPTCHA on it, and offers the existing
      case instead. Verified firing against a real CINO
- [x] Review screen (`app/ingest/page.tsx`, the "review" step) asks exactly what
      the portal cannot know: **which returned party is ours** (a select, shown
      only when both petitioner and respondent exist), which of our advocates
      hold which role (defaulting the advocate running the ingestion to
      **lead**, editable), and Firm Status (defaulting to **active**, editable).
      Party names are linked to an existing Party via the same search-or-create
      `PartyPicker` manual creation uses, pre-filled with the portal's name -
      never a silent match. Everything else from the Snapshot (CINO, case type,
      both numbers and dates, Court Status) is shown read-only and applied
      exactly as the portal reported it
- [x] `create_case_from_snapshot` (`app/services/ingest.py`) creates the Court
      (completed from the session's own district/establishment, or reused if
      already known), Case, both `CaseParty` rows (with `portal_raw_name` kept
      beside the link), Assignments, and Hearings, then marks the Snapshot
      `applied` and closes the session - all in the one `POST
      /ingest/{sid}/review` call. Only `next_hearing` (→ scheduled) and
      `last_hearing` (→ held) become Hearings; `first_hearing` is deliberately
      left out (see Findings, 2026-08-09). Tested directly against the real
      payload in `tests/test_ingest_review.py` and `tests/test_ingest_api.py`
- [x] Refresh: `CNR` tab with the stored CINO, Court's district and
      establishment pre-selected — `POST /cases/{id}/refresh` walks the portal
      from load to CAPTCHA in one call, because the advocate has nothing to
      choose. They type six digits and nothing else. `app/api/refresh.py`,
      `app/cases/[id]/refresh/page.tsx`. Refused with a 409 *before* a browser
      is opened when the Court is provisional or the Case has no CINO
- [x] Diff screen: Court Status and the court's own labels, new / changed /
      no-longer-listed Hearings with the presiding officer and whether an order
      is now available, Act & Section, Crime Details, Counsel — plus the two
      things a Refresh reports rather than acts on (a firm-recorded date the
      court is silent about, a name no Party is linked to). **Apply all or
      discard.** A discarded Snapshot is kept and marked rejected, and an
      earlier applied one becomes `superseded`
- [x] Applying takes over firm-recorded Hearings for dates it reports on, the
      court's version standing where the two disagree — while the Hearing's
      Representation and who first noted it survive untouched, both being
      firm-authored (ADR-0007)
- [x] `extract_cases` returns a **list**; `extract_case` is its single-result
      form. Every step from a response to a Case takes one element of that
      list, so the Advocate Name tab needs no parser rewrite. What bulk still
      needs is its own review UI — one Case's worth of human judgement per
      result — not a change to anything below it

---

### Unblocked, 2026-08-09

A real payload has been captured and read — see Findings below and the Parser
line above. The corpus so far is two fixtures: one found case (via CNR), one
that matched nothing (an incomplete Case No search). Every later snapshot that
turns up a shape those two don't cover should add a fixture and extend
`extract_case` rather than being special-cased silently, same as before.

## Phase 1e — Firm-side facts ✔

Four things the firm records about itself, none of them court-sourced, so a
Refresh touches none of it (rule 1, ADR-0007). Independent of 1c — do either
first. Ordered here by what depends on what.

- [x] **`relinquished`** as a fourth Firm Status value, beside active, on hold
      and closed. Not a synonym for on hold, and not derived from anything about
      the Vakalath — a purely firm-side declaration (CONTEXT.md, "Firm Status").
      Shown as a **red tag on the case list and on the case view**, because the
      damage this prevents is an advocate acting on a Case that is no longer
      ours. Four frontend places already enumerate the three values and each
      needs the fourth: `lib/api.ts` (`FirmStatus`, `FIRM_STATUS_LABEL`),
      `cases/page.tsx:19` (the filter chips), `cases/[id]/page.tsx:247`, and
      `ingest/page.tsx:700`
- [x] **Firm Status History** — an append-only record of every Firm Status
      change: from, to, which Advocate, when, and an optional reason. Makes
      `CONTEXT.md`'s attribution claim true, which it has never been: today
      `firm_status` is a bare column and `PATCH /cases/{id}` overwrites it
      leaving no trace of who or when. Written from the one place that sets the
      status, so ingestion's initial value and every later change both land in
      it. **Not on the Timeline** — surfaced from the Firm Status control on the
      case view, so the red tag can read "Relinquished — 12 Mar 2026, Anil
      Kumar"
- [x] **Vakalath** (ADR-0008) — at most one per Case, carrying a holder and
      nothing else:
      either an Advocate of the firm or an outside name in free text, never
      both. Two nullable columns on `cases` with a check constraint, exactly the
      shape `Hearing` already uses for Representation
      (`ck_hearing_representation_one`) — a separate table would hold one
      column, and a boolean beside the name would permit a yes with nobody
      named. "Yes/no" is read off whether a holder is present. No filing date,
      no explicit "no vakalath", no attribution, no note — asked and declined
      2026-08-10; add them when a real need turns up rather than up front
- [x] **Client contact details reachable.** The columns exist and always have —
      `Party.phone`, `.email`, `.address`, `.notes` (`models/people.py:53`), and
      `PartyIn`/`PartyOut` already carry them. Nothing can reach them: there is
      no `PATCH /parties/{id}`, `PartyPicker` sends only a name, and `PartyLine`
      on the case view renders none of it. So this is an API and UI task, not a
      schema one — add the patch endpoint, let the picker capture a phone on
      creation, and show phone and note against each client on the case view.
      Party-level on purpose: anything true of one Case only is an Internal Note
      (CONTEXT.md, "Party")

Already built, and *not* part of this phase despite appearing on the original
list: **per-hearing Representation**. `Hearing.represented_by_advocate_id` /
`_clerk_id`, `PUT /cases/{id}/hearings/{hid}/representation`, and the dropdown at
`Timeline.tsx:47` have been in since 2026-08-09, and a Refresh already leaves
them untouched.

## Phase 2 and beyond

Deliberately out of phase 1.

- Documents and diary attachments — Case-owned, linked optionally to a Hearing or
  Diary Entry, dated by the document itself rather than by upload, typed
  (court order / pleading / client document / correspondence), versioned. Until
  then, a refresh records only *that* the court has an order available
- Bulk ingestion via the portal's **Advocate Name** tab: one CAPTCHA returns every
  case an advocate is on in a court. The realistic way to load an existing
  backlog of a few hundred cases
- OCR for PDFs and for historical handwritten diary books
- AI semantic search across notes and documents
- Hearing reminders and notifications; calendar integration
- Cause list integration if feasible
- Client portal; analytics; role-based permissions

---

## Open questions

Answered during 1d rather than up front, by deliberate choice.

- **Does the search yield structured data we can intercept**, or do we end up
  reading rendered output after all? The handoff assumes the former. **Answered
  2026-08-06 and confirmed 2026-08-09**: yes, a Flight payload.
- **Does a result carry full hearing history**, or only current status and next
  date? **Answered 2026-08-09, corrected same day**: the *first* response to a
  search carries only three dates, as originally found. But a found case's
  detail view fires several more Server Action POSTs immediately after, one of
  which is the full hearing history (proceedings, presiding officer, purpose,
  next date per entry) — see Findings below. `submit()` was silently keeping
  only that first response and discarding the rest; it now captures all of
  them, though only the first is parsed as of this writing.
- **Can the CAPTCHA image be re-served** from the browser session with the code
  still valid? The only load-bearing one; ADR-0004 fails without it. **Answered
  2026-08-06, and the question turned out not to arise**: the image is an inline
  `data:` URI on the page, so it is read off the DOM and handed to our own page
  with nothing fetched back through the session. Confirmed in use by both
  Ingestion and Refresh since.
- **What do `reg_no` / `fil_no`'s digits mean?** A search value of `58` came
  back as `reg_no: 200058`. One example isn't enough to reverse the encoding —
  needed before the parser can produce the "MC 58/2025" shorthand a lawyer
  types, rather than the portal's raw `case_no` string.
- **What does the `type: 1` vs `type: 2` duplicate row in a search response's
  `data` mean?** The same case came back twice, identical but for that field.
  `extract_case` takes the first and ignores the second; revisit once a payload
  shows them actually differing.
- **What does "Online" mean**, shown beside Court Status ("Pending") on the
  portal's case-details page? Not investigated — nothing in any captured
  response is obviously it. Left open rather than guessed at.

## Findings

Record answers here as they are learned, with the date.

- **2026-08-05** — The portal requires a district and court to be selected before
  *any* search tab becomes usable, `CNR` included. Confirmed from direct use, not
  inferred. This is why ingestion begins at the portal (ADR-0005).

- **2026-08-06** — The portal is **https://filing.keralacourts.in/caseSearch**,
  titled "Ecourts Dashboard". Observed directly:
  - Next.js, with a **Mantine** component library on top.
  - The three selectors are Mantine `Select` widgets — an `<input>` plus a hidden
    input, **not** a native `<select>`. `select_option()` will not work; they must
    be clicked open and the `[role=option]` item chosen. Their `id`s are
    regenerated per render (`mantine-7bvna5b2f`), so **select by placeholder**:
    `Select State`, `Select District`, `Select Court`.
  - State is pre-filled to `KERALA`.
  - Before a court is chosen the page reads "Select state, district, and court to
    begin searching" — the tab bar and CAPTCHA are **not in the DOM at all**.
    Confirms ADR-0004 and ADR-0005 from the markup, not just from use.

- **2026-08-06** — **The portal refuses any client whose user agent looks
  automated.** Connections are dropped at the socket (`ERR_SOCKET_NOT_CONNECTED`,
  curl exit 000), which looks exactly like an outage or an IP ban and was briefly
  misdiagnosed as one here. It is neither: the same request with a normal browser
  user agent returns 200 immediately, and both IPs stay open throughout. Every
  browser context **must** set a realistic user agent — `USER_AGENT` in
  `app/dcms/session.py`. Playwright's default contains `HeadlessChrome` and is
  refused.

- **2026-08-06** — **The CAPTCHA is an inline `data:image/svg+xml;base64` URI**
  (~32 KB) on `img[alt=Captcha]`, not a session-bound URL. It can therefore be
  read straight off the DOM and handed to our own page, with no fetching of bytes
  back through the browser session. **This is the assumption ADR-0004 rested on,
  and it holds — more simply than expected.** The image does not rotate on a
  re-read within a second; the portal replaces it roughly every 30s.

- **2026-08-06** — **Search runs as a Next.js Server Action**: a POST to
  `/caseSearch` carrying a `next-action` header, answered with a Flight payload
  rather than a rendered page. The handoff's central assumption holds, so the
  parser reads a structured response rather than scraping HTML.

- **2026-08-06** — Page structure, all verified:
  - Tabs carry `role="tab"` with stable names — `Case No`, `CNR`, `Filing No`,
    `Party Name`, `Advocate Name`, `FIR Search`, `E-file No`, `Crl.MP`,
    `Restor.Ptn`, `Caveat`, `Judgment Search`. Their ids
    (`mantine-0f9rec8mf-tab-cnr`) contain a per-render random part, so **select
    by name, never by id**.
  - `CNR` asks for one field (`CNR Number`). `Case No` and `Filing No` also want
    `Choose Case Type` and `Year` — which is why refresh prefers CNR.
  - Case types are per court and come from the portal: Munsiff Court Ernakulam
    offers 86 of them.
  - Court names must be stored **verbatim**. The portal writes
    `Munsiff Court Ernakulam` without a comma, while neighbouring entries like
    `Munsiff Court, Aluva` have one.
  - React hydration lands *after* the inputs are painted. A click in that window
    is silently swallowed and the dropdown never opens — hence
    `HYDRATION_SETTLE_MS` and a one-retry click in `_open_dropdown`.
  - All three cascading dropdowns stay mounted in the DOM at once, so options
    must be scoped to the **visible** `[role=listbox]`, or districts get mixed in
    with states.

- **2026-08-09** — The Case No / Filing No tabs' Case Type and Year fields were
  optional in the API schema and the form, and `fill_identifier` silently
  skipped them when absent. A search submitted with only the case number (no
  type, no year) is not rejected by the portal — it is answered exactly like a
  genuine non-match, `{"status":"N"}` with no `data`, so a real case can look
  "not found" with no indication a field was ever missing. Fixed by making both
  required at every layer: `IdentifierIn` (a `model_validator`), the frontend
  form, and `fill_identifier` itself (raises rather than skips).

- **2026-08-09** — Once Case Type and Year were required, an exact-case search
  (`MC` / `58` / `2025`, a real case, confirmed found by CNR) still failed:
  `_choose()` picked `"Crl.MC"` instead of `"MC"`. The bug was in how the
  matched option was clicked, not in matching it — `match` was computed by
  exact string comparison, but the click re-queried with
  `options.filter(has_text=match)`, and Playwright's `has_text` is a
  **substring** match. `"MC"` matches both `"MC"` and `"Crl.MC"`, and `.first`
  took the wrong one. A read-back check (`_choose` and the new
  `_fill_and_verify` now read the field back after filling it and raise if it
  doesn't match) caught this immediately instead of silently submitting the
  wrong search. Fixed by clicking the exact element found while building
  `labels`, never re-querying by text. Establishment: Addl. Chief Judicial
  Magistrate Court, Thiruvananthapuram — its Case Type list holds both `MC` and
  `Crl.MC`, which is what exposed it.

- **2026-08-09** — First real payload captured and read (CNR search for
  `KLTV080027432025`, saved as `tests/fixtures/dcms_case_found.txt`). Notable:
  - The portal tracks **two separate case types** for one Case: `reg_name` /
    `regcase_type` for the registration, `file_name` / `filcase_type` for the
    filing, and they can differ (this case: registered `MC`, filed
    `Crl.MP`). Only the registration one is read as `case_type` — it is what
    lawyers mean by "case type" and what CONTEXT.md's Case Type maps to; the
    filing one is not currently kept anywhere.
  - Every date is serialised as `"$D<iso>"` with a UTC instant at `18:30:00.000Z`
    — that is IST midnight, not the UTC calendar date. Reading `.date()`
    directly reads every date **one day early**. `_parse_portal_date` converts
    to `Asia/Kolkata` first.
  - `status` at the top level (`"Pending"`) is the Court Status. `data` rows
    also carry a `status` field, seen only as `null` so far.

- **2026-08-09** — Review screen and Case creation built and scoped against
  three product decisions made deliberately rather than assumed:
  - **Party linking**: search existing Parties (the same `PartyPicker` manual
    creation uses) with a create-new fallback, pre-filled with the portal's
    name. A person always makes the final choice either way — nothing is
    linked by matching text automatically.
  - **Advocates**: at least one is required before a Case can be created, same
    as manual creation. The advocate running the ingestion defaults to
    **lead**, editable, rather than leaving the list unset.
  - **Firm Status**: defaults to **active**, editable, on the reasoning that
    most cases being ingested are ones the firm is actively taking on.
  - Only `next_hearing` and `last_hearing` become Hearings on creation;
    `first_hearing` is left out because it has so far always exactly equalled
    `date_of_filing` / `dt_regis` — it reads as the registration event, not a
    listing before the court. Revisit once a payload shows it genuinely
    differing from the filing/registration date.
  - The Court is completed (not left provisional) at this same step, from the
    session's own `state`/`district`/`court` — the wizard already holds the
    portal's exact words, so there is nothing to be provisional about. This
    means `POST /ingest/{sid}/review` must run inside the same session that did
    the search; a Snapshot cannot yet be reviewed after that session has ended
    (idle timeout, or the advocate leaving the page). It is still kept per rule
    3 either way — only the Court/Case creation step is unavailable, not the
    Snapshot itself. Revisit if that turns out to matter in practice.

- **2026-08-09** — A user-pasted "Case Details" view from the portal (same
  case as the fixtures: CNR `KLTV080027432025`) showed far more than
  `extract_case` reads: E-File No, Disposed Date, Acts & Section, a full
  hearing-history timeline with a presiding officer per entry, Crime Details
  (FIR/CR/police station/officer), and multiple advocates per party over time.
  Checked directly against the captured fixture first, not assumed: none of
  those keys or words exist anywhere in `dcms_case_found.txt` — not "read
  further into the same payload", genuinely absent from it.
  **Root cause, found by driving a live CNR search for this case with full
  network capture (`scripts/probe_case_detail.py`, one CAPTCHA, solved live)**:
  a found case fires **ten** Server Action POSTs to `/caseSearch` in quick
  succession, not one. `submit()` only ever awaited and returned the first and
  silently threw the rest away. The other nine, by shape:
  - additional party/advocate rows (`pet_res`/`adv_name`/`adv_code` — a party
    can have more than one representing advocate over the life of a case,
    which the first response's single `pet_adv`/`res_adv` field cannot hold)
  - order metadata (`order_no`, `doc_type`, `order_dt`, `docu_name`)
  - the hearing-history timeline (`purpose_name`, `next_date`, `todays_date`,
    `order_remark`, `names` — the presiding officer, one row per hearing)
  - Acts & Section (`acts`, `actname`, `section`)
  - Crime Details (`crno`, `fir_no`, `fir_year`, `fir_date`, `investofficer`,
    `police_st_name`, `rank`)
  - three empty arrays, for categories this case has none of
  **Fixed**: `portal.submit()` now returns every response it sees for a
  10-second window after the click (`FOLLOWUP_WINDOW_MS`), not just the first;
  `flight.join_responses`/`split_responses` combine them into the one
  `raw_response` Text column on a separator byte confirmed absent from real
  payloads, so nothing a CAPTCHA paid for is lost (rule 3). `extract_case`
  still reads only the first response — parsing the other nine into the model
  is deliberately **not done yet**, because it raises real vocabulary
  questions paused mid-session: is Crime Details Case-level or its own thing,
  does `Hearing` gain a presiding-officer field, how does a second advocate
  per party get recorded when `CaseParty` only holds one name today. Fixture:
  `tests/fixtures/dcms_case_detail_burst.txt` (all nine, real, same case),
  `tests/test_flight.py::TestMultipleResponses`.

- **2026-08-09** — The additional-party-rows response (one of the nine above)
  carries its own `type` field, distinct from the main search response's
  type-1-vs-type-2 duplicate row (still unanswered, see Open Questions). Here
  all six rows are `type: 2`, and all six are this case's *respondent* side
  (`BINU S L and ANOTHER`, `Leela R`) — consistent with `type` meaning
  petitioner/respondent in this endpoint specifically, though no `type: 1` row
  came back to compare against, and nothing here should be assumed to explain
  the other endpoint's `type`. The same six rows also show counsel changing
  over the case's life by timestamp (`create_modify`): `AJITH R` from
  2025-10-29, `ASHEER A K` added 2026-07-01 — real evidence for Counsel being
  a list that grows, not a name that gets overwritten.

- **2026-08-09** — Vocabulary session (grill-with-docs) for the nine
  unparsed responses, resolved and written into CONTEXT.md:
  - **Crime Details** is its own entity, one-to-one with `Case`, not columns
    on `Case` directly — most Cases will never have one, and CONTEXT.md's
    Court entity is the precedent for a portal-derived thing living apart.
  - **Act & Section** is a list per `Case`, one row per act/section pair,
    replaced wholesale on every Ingestion/Refresh like everything else in that
    bucket.
  - **Counsel** is now a defined term (was only ever a banned word under
    Advocate) — the other side's lawyer, a list per `CaseParty`, never a
    system user.
  - **Presiding Officer** is a new court-sourced-only field the Hearing
    concept needs — deliberately distinct from an *investigating* officer
    (Crime Details) and a *Protection* Officer (named in this case's own
    proceedings text under the DV Act), which are different people.
  - **Clerk** is a new kind of firm member — named, no login, distinct from
    Advocate.
  - **Representation** is a new single field per Hearing — an Advocate or a
    Clerk on record for that date, set before or after it, entered by a
    person, never by a refresh. This supersedes half of the `Assignment`
    entry's old wording ("who turned up is a Diary Entry matter") — that
    sentence was written before Representation existed and has been corrected
    in place.
  - `E-File No` and `Disposed Date` need no glossary entry — plain nullable
    `Case` columns, same bucket as `case_type`, no subtlety worth writing down.
  - None of this is modeled or persisted yet — schema, parser and API changes
    are the next session's work, not this one's.

- **2026-08-09** — The above built end to end, against the real capture:
  - Models: `Clerk` (`clerks`), `CrimeDetail` (one-to-one with `Case`),
    `ActSection` (list per `Case`), `Counsel` (list per `CaseParty`). `Hearing`
    gained `presiding_officer`, `represented_by_advocate_id`,
    `represented_by_clerk_id` with a check constraint that at most one of the
    latter two is set. Migration `3210902b9f8e`
  - `app/dcms/flight.py::extract_case_detail` reads the other nine responses,
    classified by the keys their rows carry rather than by position (nothing
    guarantees the burst always lands in the same order). Verified against
    `tests/fixtures/dcms_case_detail_burst.txt`: all ten real hearings recover
    with the right presiding officer, purpose and outcome; both real counsel
    names recover for the one respondent; the one act/section and the
    (mostly-empty) Crime Details row both recover
  - `services/ingest.py::create_case_from_snapshot` now creates the *full*
    hearing history from the burst (not just next/last), each with its
    presiding officer, and marks `order_available` from the order-metadata
    response; creates `CrimeDetail` whenever the row has anything at all in
    it (this case's is mostly null but keeps `police_station`); creates every
    `ActSection`; attaches `Counsel` rows to whichever `CaseParty` matches the
    portal's petitioner/respondent side. Falls back to the old next/last-only
    Hearing logic when a Snapshot's burst is thin or absent (e.g. today's
    existing tests, which only ever captured one response) — nothing regresses
  - `PUT /cases/{id}/hearings/{hid}/representation` sets or clears a Hearing's
    Representation, deliberately **outside** the court-source edit lock
    (ADR-0002's guard is about the court's own account - purpose, outcome,
    date - not this firm-only field). `POST/GET /clerks` for creating and
    listing Clerks, no login, per CONTEXT.md
  - Not done: any frontend display of this. Every field above is stored and
    returned by the API (`CaseDetail.crime_details`/`.act_sections`,
    `CasePartyOut.counsels`, `HearingOut.presiding_officer`/
    `.represented_by_advocate`/`.represented_by_clerk`) but nothing in
    `frontend/` renders any of it yet
  - Not done: none of this runs on **Refresh** yet, because Refresh itself
    isn't built (still unchecked below) - only Ingestion creates a Case today.
    `create_case_from_snapshot` is Ingestion-only; applying a later Snapshot's
    full detail onto an *existing* Case (taking over its Hearings, replacing
    its Act & Section list wholesale, etc.) is unwritten and will need its own
    care once the diff/apply screen exists
  - 77 tests passing (was 60): `tests/test_flight.py::TestExtractCaseDetail`,
    `tests/test_ingest_review.py::TestCreateCaseFromSnapshotWithFullDetail`,
    `tests/test_record.py::TestRepresentation`, `tests/test_clerks.py`

- **2026-08-10** — **Refresh built, and rule 1 restated as ADR-0007.** The old
  wording ("Hearings and Court Status, and nothing else") was written before a
  Snapshot carried anything else worth writing, and CONTEXT.md had already
  overtaken it in two places — Act & Section is "replaced wholesale by every
  Ingestion and Refresh", and a Case "never gains Crime Details by anything
  other than a Refresh". Restated by what it protects: every court-sourced fact
  is replaced wholesale, and nothing a person entered is touched. The
  registration number is the concrete case — a plaint filed in March is
  registered in June, and learning that number without anyone retyping it is a
  large part of what Refresh is for.

- **2026-08-10** — **Saying nothing is not saying none.** The trap in applying a
  Snapshot to an existing Case: a thin capture (burst never arrived, or an older
  Snapshot from before `submit()` captured the follow-ups) reports no acts and
  no crime details in exactly the same words as a case that genuinely has none.
  Applying the first over the second wipes what an earlier, fuller Refresh
  correctly recorded. Fixed by having the parser record *which shapes arrived*
  (`PortalCaseDetail.kinds_seen`) rather than only what was in them; every
  wholesale replacement is gated on that. The same rule applies field by field:
  a `None` from the portal leaves the existing value alone rather than clearing
  it. Known limit, stated in `_classify_rows`: an *empty* response carries no
  keys to classify by, so it is indistinguishable from one that never came, and
  a genuinely-emptied block will not clear. The error runs in the safe
  direction; fix it against a real capture where that happens, not by guessing
  at burst order now.

- **2026-08-10** — **`filing_date` and `registration_date` were a day early on
  every ingested Case**, found by the refresh diff reporting them as changed on
  a Snapshot identical to the one the Case was built from. They were
  `timestamptz` columns holding what is conceptually a date: writing a `date`
  stores IST midnight, and reading that instant back as UTC gives the previous
  evening. The same trap as the portal's own `$D` encoding
  (`_parse_portal_date`), one layer further in — and it would have made every
  future Refresh report two spurious changes forever. Both are `Date` columns
  now; migration `7c41ab0d9e52` converts existing values in `Asia/Kolkata`, so
  the day that was meant is recovered rather than shifted again. Neither field
  was ever exposed in `CaseSummary`/`CaseDetail`, so nothing had displayed the
  wrong day to an advocate yet.

- **2026-08-10** — Three decisions taken while building the diff, each written
  into ADR-0007 rather than left in the code:
  - **Deciding is untied from the portal session.** Ingestion's review must run
    inside its own session because the Court is completed from it; a Refresh's
    Court is already complete, so `submit()` closes the browser as soon as the
    response is stored and apply/discard work off the Snapshot alone. An
    advocate interrupted mid-refresh comes back to a decision still waiting,
    not a stranded session — which also removes the caveat recorded on
    2026-08-09 for Ingestion, for the Refresh path at least.
  - **The diff is recomputed at apply time**, against the Case as it stands
    rather than the plan the browser is holding. Two advocates deciding at once
    cannot apply a plan that has stopped being true.
  - **Counsel is matched to a `CaseParty` by `portal_raw_name`** — the portal's
    own words, stored verbatim beside the link at Ingestion — never by the
    Party name a person chose. Matching evidence to evidence is a lookup;
    matching a portal string to a human's chosen name would be exactly the
    silent linking ADR-0005 forbids. A name with no `CaseParty` is reported on
    the screen and left.

- **2026-08-10** — A real before-and-after fell out of the two existing
  fixtures rather than needing a hand-edited payload: `dcms_case_found.txt` is
  the bare search response (two dates, no acts, no crime details, no counsel)
  and `dcms_case_detail_burst.txt` is the whole burst for the *same* case.
  Ingesting from the first and refreshing with the second is an honest refresh
  — same case, more of the court's account — and exercises every block a
  Refresh writes. `tests/test_refresh.py`, 25 tests. Total 105 (was 80).

- **2026-08-10** — **`Counsel` holds our own side's advocate too, and the
  glossary says it must not.** `services/ingest.py:169` runs the counsel loop
  over both sides, so where our client is the petitioner, the portal's
  petitioner-advocate — very often one of our own five — is written as a
  `Counsel` row against our client's `CaseParty`. `CONTEXT.md` defines Counsel
  as "the other side's lawyer… never conflated with Advocate". The code has done
  exactly that since ingestion was built, and Refresh inherited it.

  **Deliberately left alone for now** (decided 2026-08-10), so the Vakalath does
  not wait on it. The options weighed were: widen Counsel to mean any lawyer the
  portal names against a `CaseParty` and correct the glossary; give our side's
  portal advocate its own court-sourced entity; or stop ingesting it and lose
  the court's own view of who represents us. The last is the only one that loses
  data, and it loses the single independent check on whether a vakalath actually
  reached the file — so prefer one of the first two whenever this is picked up.
  Until then the Vakalath is purely firm-entered and the duplication stands.
  ADR-0008 explains why the Vakalath is unaffected by which way this goes.

- **2026-08-10** — **Phase 1c built.** Migration `63c137204a1f`. Two traps, both
  found by checking rather than by being bitten:
  - **A text-search config passed as a Python string becomes a bind
    parameter.** `func.to_tsvector("english", col)` compiles to
    `to_tsvector(%(param)s, body)`, which is correct SQL, returns the right
    rows, and can never use a functional index — every search would have been a
    sequential scan while an unused GIN index sat beside it. It has to be a
    `literal_column("'english'")` so the expression matches the index's
    byte-for-byte. `EXPLAIN` with `enable_seqscan=off` confirms the planner now
    picks `ix_diary_entries_body_fts`. The two-argument `to_tsvector(regconfig,
    text)` is IMMUTABLE, which is what makes indexing it legal; the
    one-argument form depends on a session setting and is not.
  - **Indexes that exist only in a migration read as drift.** With the GIN
    indexes created by raw `op.execute` and absent from the models,
    `alembic check` reported two `remove_index` operations — meaning the next
    autogenerate would have proposed dropping them, and a later session would
    probably have accepted it. They are now declared on `DiaryEntry` and
    `InternalNote` with `Index(..., text("to_tsvector('english', body)"),
    postgresql_using="gin")` as well, and `alembic check` is clean.

  Also: **"today" now means today in Kerala.** The dashboard asks what is
  listed this week, and `date.today()` answers with the *server's* local day —
  which is the right answer only for as long as the office server stays on IST.
  `app/config.py` grows `IST` and `today_in_court()`, and `flight.py`'s private
  `_IST` now points at the same constant rather than declaring its own. A court
  date is a calendar day, not an instant; this is the same family of mistake as
  the timestamptz-versus-date bug recorded against `Case.filing_date`.

  Also: `_task_or_404` needs `populate_existing=True` for exactly the reason
  `load_case` documents — the instance is already in the identity map from the
  write just done, so ticking a task off reported a stale `done_by`. Two tests
  caught it.

- **2026-08-10** — **Phase 1e built.** Migration `e8b56b3a25aa`. Three things
  worth knowing:
  - `firm_status` is a **non-native enum**, so it is a plain `VARCHAR` sized to
    the longest value — `VARCHAR(7)` for `on_hold`. Adding `relinquished` (12
    characters) is therefore a column *type* change, not a free enum addition,
    and the downgrade has to move any relinquished rows out before narrowing it
    back. Mapped to `closed` rather than `on_hold`, since on hold means the firm
    still holds the Case, which is the one thing a relinquished Case is not.
    Any future value longer than the current maximum has the same trap.
  - The migration **backfills an opening Firm Status History entry** for every
    Case that already existed, taking the Case's own `created_at` rather than
    `now()` — the status was set then, and the history would otherwise claim
    every old Case was opened on migration day. Verified against the dev
    database.
  - The `Vakalath` is two nullable columns on `cases` rather than its own table,
    since it carries only a holder. `tests/test_firm_side_facts.py` (26 tests)
    covers it, including the one that matters most: a real Refresh applied over
    a Case with a Vakalath and a relinquishment leaves both untouched (rule 1,
    ADR-0007) — refreshed for real against the fixtures, not asserted by reading
    the source.

  Tests build the schema from `Base.metadata`, not from migrations, so a
  migration is only ever proved by running it. `uv run alembic check` reports no
  drift between the two.

- **2026-08-10** — **Design pass over the whole frontend.** No behaviour, no API
  and no vocabulary changed; every screen was restyled. `frontend/DESIGN.md` is
  the reference. Three things worth knowing:
  - **Provenance is now visual.** Court-sourced facts carry a teal rule and a
    `▪`; firm-authored ones a blue rule and a `¶`. This is rule 1 made legible
    rather than decoration: a court-reported Hearing and a firm-recorded one on
    the same date are told apart without reading, and the case detail is split
    into *The firm's own* and *From the court* sheets so that what a Refresh
    replaces wholesale is exactly one visible block. Blue doubles as the
    interaction colour, on the same reasoning — an interaction is the firm's
    hand, and this application is the firm's record.
  - **Fonts are vendored, not fetched.** `app/fonts/` holds five woff2 files
    (Newsreader, Libre Franklin, Spline Sans Mono — all SIL OFL, licences
    beside them) loaded through `next/font/local`. The old `layout.tsx` comment
    ruled out web fonts so the office server could build and run offline;
    `next/font/google` downloads at build time and would have broken that,
    `next/font/local` does not.
  - **Tailwind theme, not ad-hoc vars.** `globals.css` declares the palette once
    and exposes it through `@theme inline`, so `text-court`, `border-rule` and
    `bg-firm-wash` exist as utilities and follow `prefers-color-scheme`
    automatically. The old `text-[color:var(--muted)]` spelling is gone from
    every file.

  What has **not** been seen rendered: the Ingestion and Refresh screens. Both
  open a live Playwright session against DCMS the moment the page mounts, and
  fetching from the portal unasked is precisely what rule 3 forbids. They
  compile and their markup shares the primitives every other screen was checked
  with, but somebody should look at them the next time a real ingestion is run.

- **2026-08-10** — **Recolour, and the accessibility defects it exposed.** The
  first pass used a warm cream-and-oxblood palette; it read as dark brown in the
  dark theme and was replaced with a cool one — bond-paper grey-blue, slate-navy
  at night, blue as the accent. The structure, typography and every rule below
  are unchanged. What is worth knowing is not the hues but the system:
  - **Four hues, one job each, and one of them is now rare.** `--firm` blue is
    the firm's own hand *and* every interaction; `--court` teal is what DCMS
    reported; `--danger` red is relinquishment, errors and destructive acts and
    **nothing else**; `--caution` amber is a date that passed with nothing
    recorded. Previously the firm's mark and the Relinquished stamp shared a
    hue, which cost the stamp some of its force. Red now appears nowhere else,
    so it is the loudest thing on any page it lands on.
  - **Colour is never the only signal.** Every provenance mark keeps its glyph
    and every panel keeps its `The firm` / `The court` label, so the palette can
    move again without inverting the distinction. It nearly did here: the
    Timeline hint said "anything on a blue rule is the court's account", which
    the recolour made exactly backwards. It no longer names a colour at all.
  - **Contrast was measured, and three things failed.** Every pair was computed
    rather than eyeballed. `--ink-faint` — which carries every small-caps label
    — was **2.81:1** on paper, well under 4.5:1. Control borders were **1.3:1**,
    meaning a text field's boundary was effectively invisible; `--edge` is now a
    third line token, separate from the two decorative ones, held at 3:1 per
    WCAG 1.4.11. And white on a solid accent is 2.4:1 once the accents lighten
    for dark mode, so `--on-accent` flips to dark there.
  - **Two defects from the previous pass, fixed here.** `.field-input` set
    `outline: none` on `:focus`, which silently removed the keyboard focus ring
    from every input in the app; a `:focus-visible` rule restores it. And inputs
    were 13px, which makes iOS zoom the whole page on focus — they are 16px
    below the `sm` breakpoint and step down above it.

- **2026-08-10** — **A theme control, which the recolour had left missing.**
  Until now the palette followed `prefers-color-scheme` and nothing else, so an
  advocate on a dark-set laptop had no way to work in light. Light / system /
  dark now sits in the masthead, and again on the sign-in screen because that
  one renders outside the app shell.
  - **Three states, not a switch.** A two-state toggle cannot express "follow
    the OS", which is the default and where most people will leave it. The
    stored value is the preference; `data-theme` on `<html>` is always a
    resolved `light` or `dark`.
  - **The resolution happens before the first paint**, in an inline `<head>`
    script, per Next's own `preventing-flash-before-hydration` guide. `useEffect`
    runs after paint and `useLayoutEffect` after hydration — both would show a
    white flash on the way into dark mode. Verified: at document `commit`, well
    before hydration, `data-theme` already reads `light` for a stored light
    preference on a dark-set OS.
  - **One consequence worth the trouble:** because the script resolves "system"
    rather than leaving it to CSS, `globals.css` holds each palette exactly
    once. No `prefers-color-scheme` block duplicating the dark values, so they
    cannot drift apart.
  - **`useSyncExternalStore`, not state synced from an effect.** `localStorage`
    is external mutable state; reading it that way keeps the server and
    hydration renders in agreement and satisfies `react-hooks/set-state-in-effect`,
    which correctly rejected the first attempt.
  - **A latent bug the toggle exposed.** The date picker's icon was inverted by
    hand under a `prefers-color-scheme` rule. That keys off the OS, so the
    moment the theme could be chosen independently it inverted the wrong way —
    invisible icon on a dark field for anyone running dark-on-a-light-OS. Each
    palette now declares `color-scheme`, which does the job properly and also
    fixes native scrollbars and form controls. Checked in exactly that
    configuration.
