# Project Handoff – Law Firm Case Repository & DCMS Integration

## Objective

Build a lightweight case management system for a small law firm (approximately five advocates). The application should become the firm's primary repository for all case-related information, while integrating with the Kerala DCMS portal only when advocates need to refresh official court information.

---

## Core Philosophy

**Our application is the source of truth.**

The Kerala DCMS portal should **not** be treated as the primary database. Instead, it acts as an external reference used to retrieve the latest official case information on demand.

The majority of data (notes, diary entries, documents, reminders, tasks, etc.) will live exclusively in our application.

---

## Core Features

### Case Management

Each case should store:

* Case Number
* CINO
* Court
* Case Type
* Client(s)
* Opposite Party
* Assigned Advocate
* Current Status
* Next Hearing Date
* Timeline
* Documents
* Internal Notes
* Daily Proceedings / Diary Entries
* Tasks
* Tags

---

### Search

Support searching by:

* Case Number
* CINO
* Client Name
* Opposite Party
* Advocate
* Court
* Judge (future)
* Hearing Date
* Keywords within diary entries
* Keywords within uploaded documents (future OCR)

---

### Daily Diary

Each diary entry should contain:

* Date
* Proceedings
* Orders
* Next Hearing
* Follow-up Tasks
* Attachments

The diary should form a chronological timeline for every case.

---

## DCMS Integration Strategy (Primary Workflow)

**Refresh only when required.**

Do **not** periodically scrape or synchronize every case.

Instead, provide a **"Refresh from DCMS"** button on every case page.

Workflow:

1. Advocate opens a case in our application.
2. Clicks **Refresh from DCMS**.
3. Playwright launches the official Kerala DCMS Case Search page.
4. Case details are pre-filled automatically.
5. Advocate manually enters the CAPTCHA.
6. Search executes.
7. Application extracts the returned structured data.
8. Local database is updated.
9. Any changes are highlighted to the advocate.

This keeps CAPTCHA interactions to a minimum while avoiding unnecessary traffic to the official portal.

---

## Playwright Integration Plan

Playwright is **not** intended for HTML scraping.

Use it as a browser automation layer that interacts with the official website exactly as a normal user would.

Responsibilities:

* Open the DCMS Case Search page.
* Populate search fields.
* Wait for the advocate to complete the CAPTCHA.
* Submit the search.
* Capture the returned structured response.
* Parse the response.
* Update the local database.
* Download and attach documents if this becomes possible in future phases.

Avoid parsing rendered HTML whenever structured responses are available.

---

## Current Findings

The Kerala DCMS portal:

* Uses Next.js App Router.
* Uses React Server Components (Flight protocol).
* Search requests are sent via Server Actions.
* Structured case data is returned rather than traditional HTML pages.
* CAPTCHA refreshes every 30 seconds.
* CAPTCHA should always be solved manually.

No attempt should be made to bypass or defeat CAPTCHA or other portal security mechanisms.

---

## Data Synchronization

Whenever a refresh succeeds:

Compare new data against the existing record.

Examples:

* Status changed
* Hearing date changed
* New order uploaded
* New proceedings available

Display a concise summary of changes before saving.

---

## Future Enhancements

* OCR for uploaded PDFs
* OCR for historical handwritten diary books
* AI-powered semantic search across notes and documents
* Hearing reminders
* Calendar integration
* Cause list integration (if feasible)
* Client portal
* Analytics dashboard
* Role-based permissions
* Full document version history

---

## Suggested Technology Stack

Backend:

* FastAPI

Frontend:

* Next.js / React

Database:

* PostgreSQL

Document Storage:

* Local filesystem (upgradeable to S3-compatible storage)

Authentication:

* JWT / Session-based authentication

Automation:

* Playwright

Search:

* PostgreSQL Full Text Search initially
* Vector search (Qdrant) in a later phase

---

## Development Priority

1. Case management
2. Diary entries
3. Search and filtering
4. Document uploads
5. "Refresh from DCMS" integration
6. Difference detection after refresh
7. AI and OCR features

The initial goal is reliability and ease of use for advocates, not full automation.
