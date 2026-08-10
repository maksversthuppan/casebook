# Working in this repository

A case management system for a small Kerala law firm (five advocates). **This
application is the source of truth.** The Kerala DCMS portal is an outside
reference consulted one case at a time, on demand, with a human solving the
CAPTCHA.

## Read these before doing anything

| File | What it is |
|---|---|
| `CONTEXT.md` | The vocabulary. Definitions and the words to avoid |
| `docs/adr/` | The decisions, and why they were made |
| `ROADMAP.md` | The phased plan, current status, open questions, findings |
| `handoff.md` | The original brief. **Superseded in several places** — see below |

`CONTEXT.md` and the ADRs are the authority. If the roadmap, the code, or
anything I say disagrees with them, they win.

## Use the project's vocabulary

`CONTEXT.md` is not decoration. Several terms were sharpened precisely because
the loose version hid a real distinction, and the banned words are banned for
concrete reasons:

- **`case number`** — say `filing number` or `registration number`; neither is
  identity. Identity is internal, with **CINO** as the DCMS match key
- **`current status`** — say **Court Status** (from DCMS) or **Firm Status**
  (ours). They legitimately disagree
- **`sync` / `poll` / `scrape`** — say **Refresh** or **Ingestion**. Nothing here
  is automatic or recurring
- **`daily proceedings`** — a **Hearing** is the court's listing; a **Diary
  Entry** is what an advocate wrote. Two different records
- **`assigned advocate`** — a Case has several advocates, each with a role

## Non-negotiable rules

Full list in `ROADMAP.md`; these three cause real damage if broken.

1. **A refresh replaces every court-sourced fact, and nothing else.** Court
   Status, Hearings, the court's own labels, Act & Section, Crime Details,
   Counsel — all replaced wholesale. Never a Diary Entry, Note, Task, Firm
   Status, Representation or linked Party. (ADR-0002, ADR-0007)
2. **A snapshot is applied whole or discarded whole.** No per-field picking.
3. **The CAPTCHA is always solved by a person.** Never read, guessed, bypassed or
   automated, and nothing is ever fetched on a schedule or in bulk. (ADR-0003)

## Where the handoff is out of date

`handoff.md` is the original brief and is kept for provenance. It has since been
overtaken on: `Daily Proceedings / Diary Entries` (two concepts), `Current
Status` (two fields), `Case Number` and `CINO` (not peers), `Assigned Advocate`
(several), `Next Hearing Date` (derived), clients and opposite parties (one Party
entity with roles), and case creation (normally ingested from the portal, not
typed in). Documents have moved to phase 2.

## Stack

FastAPI · PostgreSQL · Next.js 16 · Playwright · session auth. One office server
runs everything, including the Playwright browser. All five advocates read and
write everything; authorship is recorded rather than permissions enforced.

## Running it

```bash
docker compose up -d                     # Postgres on host port 5433

cd backend
uv sync
cp .env.example .env                     # defaults match docker-compose
uv run alembic upgrade head
uv run python -m scripts.seed            # writes backend/credentials.txt
uv run pytest                            # 161 tests
uv run uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev                              # http://localhost:3000
```

The frontend proxies `/api/*` to the backend (`next.config.ts`), so the browser
sees a single origin and the session cookie needs no CORS handling. Override the
backend location with `BACKEND_URL`.

Notes for whoever picks this up:

- Table names are **plural** (`cases`, `parties`, `assignments`) — `case` is a
  reserved SQL keyword.
- The backend is **async throughout** (asyncpg, async SQLAlchemy). This was
  chosen for phase 1d, where Playwright sessions are held across requests.
- Tests use a separate `dcms_test` database, created automatically on first run.
- Passwords are argon2 hashes and cannot be read back. If one is lost, issue a
  new one with `uv run python -m scripts.seed --reset <email>`. Generated
  passwords are appended to `backend/credentials.txt`, which is gitignored and
  meant to be deleted once handed over.
