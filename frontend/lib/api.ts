export type FirmStatus = "active" | "on_hold" | "relinquished" | "closed";
export type PartyRole = "client" | "opposite_party";
export type AdvocateRole = "lead" | "assisting" | "appearing";
export type RelationKind = "appeal_of" | "execution_of" | "connected_to";

export interface Advocate {
  id: string;
  name: string;
  email: string;
}

export interface Party {
  id: string;
  name: string;
  kind: "person" | "organisation";
  phone: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
}

export interface Court {
  id: string;
  name: string;
  portal_state: string | null;
  portal_district: string | null;
  portal_establishment: string | null;
  /** A provisional court cannot be searched on DCMS until Ingestion identifies it. */
  is_complete: boolean;
}

/** The other side's lawyer, as the portal names them. Never a system user -
 *  see CONTEXT.md, "Counsel". A CaseParty may carry several at once. */
export interface Counsel {
  id: string;
  name: string;
  registration: string | null;
}

export interface CaseParty {
  id: string;
  role: PartyRole;
  position: number;
  portal_raw_name: string | null;
  party: Party;
  counsels: Counsel[];
}

/** A firm member recorded by name, with no login of their own - see
 *  CONTEXT.md, "Clerk". */
export interface Clerk {
  id: string;
  name: string;
}

/** The police case a Case relates to. Present only where the court records
 *  one - most Cases have none (ADR-0006). */
export interface CrimeDetail {
  id: string;
  cr_no: string | null;
  fir_no: string | null;
  fir_year: number | null;
  fir_date: string | null;
  investigating_officer: string | null;
  police_station: string | null;
  rank: string | null;
}

/** One law and section a Case is brought under. A Case carries a list of
 *  these - see CONTEXT.md, "Act & Section". */
export interface ActSection {
  id: string;
  act_code: string | null;
  act_name: string;
  section: string | null;
}

export interface Assignment {
  id: string;
  role: AdvocateRole;
  advocate: Advocate;
}

export interface CaseSummary {
  id: string;
  cino: string | null;
  registration_number: string | null;
  filing_number: string | null;
  case_type: string | null;
  court: Court;
  /** The court's word, in the portal's vocabulary. Never written by hand. */
  court_status: string | null;
  /** The firm's own view. This is what every list filters on. */
  firm_status: FirmStatus;
  last_refreshed_at: string | null;
  /** Read off the hearings, never stored. May be in the past — meaning a date
   *  went by with no outcome recorded, which wants attention. */
  next_hearing_date: string | null;
  parties: CaseParty[];
  assignments: Assignment[];
}

export interface CaseDetail extends CaseSummary {
  tags: { id: string; name: string }[];
  created_at: string;
  updated_at: string;
  crime_details: CrimeDetail | null;
  act_sections: ActSection[];
  /** The Vakalath: at most one of these two, and often neither. The firm's own
   *  claim about who is on record - deliberately not the advocate the portal
   *  names for our side, which may legitimately disagree (ADR-0008). */
  vakalath_advocate: Advocate | null;
  vakalath_holder_name: string | null;
}

/** One entry of the Firm Status History. Append-only, so `created_at` is when
 *  the change was made. Deliberately not part of the Timeline. */
export interface FirmStatusChange {
  id: string;
  from_status: FirmStatus | null;
  to_status: FirmStatus;
  reason: string | null;
  changed_by: Advocate | null;
  created_at: string;
}

export type HearingState = "scheduled" | "held" | "superseded" | "unrecorded";
export type HearingSource = "firm" | "court";

export interface Hearing {
  id: string;
  date: string;
  state: HearingState;
  /** "court" means DCMS has spoken about this date; it is then read-only. */
  source: HearingSource;
  purpose: string | null;
  outcome: string | null;
  order_available: boolean;
  recorded_by: Advocate | null;
  /** The judge or magistrate who sat on this Hearing. Court-sourced only. */
  presiding_officer: string | null;
  /** Who is on record as having represented the firm here - firm-authored,
   *  settable regardless of `source` (CONTEXT.md, "Representation"). */
  represented_by_advocate: Advocate | null;
  represented_by_clerk: Clerk | null;
}

export interface DiaryEntry {
  id: string;
  date: string;
  body: string;
  author: Advocate;
  created_at: string;
  updated_at: string;
}

export interface InternalNote {
  id: string;
  body: string;
  author: Advocate;
  created_at: string;
  updated_at: string;
}

/** Something an Advocate owes on a Case. `due_on` is what the deadline actually
 *  falls on today: for a task due before the next hearing it is read off the
 *  Case's scheduled Hearings, so moving the court date moves it with nothing
 *  edited. Null means no deadline — or no hearing scheduled yet to be due
 *  before (CONTEXT.md, "Due before the next hearing"). */
export interface Task {
  id: string;
  case_id: string;
  title: string;
  assignee: Advocate;
  due_date: string | null;
  due_before_next_hearing: boolean;
  due_on: string | null;
  done_at: string | null;
  done_by: Advocate | null;
  diary_entry_id: string | null;
  created_at: string;
}

/** Why a case came back from the search box. For diary and note hits the
 *  snippet marks the match with `<<` and `>>`. */
export interface SearchMatch {
  kind: "identifier" | "party" | "diary" | "note";
  snippet: string | null;
}

export interface SearchHit {
  case: CaseSummary;
  matches: SearchMatch[];
}

export interface Dashboard {
  today: string;
  /** The last day counted as "this week" — shown, rather than left to guess. */
  horizon: string;
  stale_after_days: number;
  hearings: { hearing: Hearing; case: CaseSummary }[];
  /** Scheduled dates that passed with nothing recorded against them. */
  hearings_passed: { hearing: Hearing; case: CaseSummary }[];
  tasks: Task[];
  stale_cases: CaseSummary[];
}

export type TimelineItem =
  | { kind: "hearing"; date: string; hearing: Hearing }
  | { kind: "diary"; date: string; entry: DiaryEntry };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function describe(body: unknown): string {
  if (typeof body === "string") return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: surface the message, not the whole shape.
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc.slice(1).join(".") : "";
          return field ? `${field}: ${d.msg}` : (d.msg ?? "invalid");
        })
        .join("; ");
    }
  }
  return "Something went wrong";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (res.status === 204) return undefined as T;

  const body = res.headers.get("content-type")?.includes("json")
    ? await res.json()
    : await res.text();

  if (!res.ok) throw new ApiError(res.status, describe(body));
  return body as T;
}

export const api = {
  me: () => request<Advocate>("/auth/me"),
  login: (email: string, password: string) =>
    request<Advocate>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  advocates: () => request<Advocate[]>("/auth/advocates"),

  courts: (q?: string) =>
    request<Court[]>(`/courts${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  parties: (q?: string) =>
    request<Party[]>(`/parties${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  casesForParty: (id: string) => request<CaseSummary[]>(`/parties/${id}/cases`),

  cases: (params: { q?: string; firm_status?: FirmStatus; mine?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.firm_status) qs.set("firm_status", params.firm_status);
    if (params.mine) qs.set("mine", "true");
    const s = qs.toString();
    return request<CaseSummary[]>(`/cases${s ? `?${s}` : ""}`);
  },
  case: (id: string) => request<CaseDetail>(`/cases/${id}`),
  createCase: (payload: unknown) =>
    request<CaseDetail>("/cases", { method: "POST", body: JSON.stringify(payload) }),
  updateCase: (id: string, payload: unknown) =>
    request<CaseDetail>(`/cases/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  firmStatusHistory: (id: string) =>
    request<FirmStatusChange[]>(`/cases/${id}/firm-status-history`),
  /** Give neither field to clear the Vakalath; never both at once. */
  setVakalath: (id: string, payload: { advocate_id?: string | null; holder_name?: string | null }) =>
    request<CaseDetail>(`/cases/${id}/vakalath`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  updateParty: (
    id: string,
    payload: { name?: string; phone?: string | null; notes?: string | null },
  ) => request<Party>(`/parties/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  timeline: (id: string) => request<TimelineItem[]>(`/cases/${id}/timeline`),

  recordHearing: (
    id: string,
    payload: { date: string; state?: HearingState; purpose?: string | null; outcome?: string | null },
  ) => request<Hearing>(`/cases/${id}/hearings`, { method: "POST", body: JSON.stringify(payload) }),
  amendHearing: (id: string, hearingId: string, payload: unknown) =>
    request<Hearing>(`/cases/${id}/hearings/${hearingId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteHearing: (id: string, hearingId: string) =>
    request<void>(`/cases/${id}/hearings/${hearingId}`, { method: "DELETE" }),
  setRepresentation: (
    id: string,
    hearingId: string,
    payload: { advocate_id?: string | null; clerk_id?: string | null },
  ) =>
    request<Hearing>(`/cases/${id}/hearings/${hearingId}/representation`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  clerks: () => request<Clerk[]>("/clerks"),
  createClerk: (name: string) =>
    request<Clerk>("/clerks", { method: "POST", body: JSON.stringify({ name }) }),

  writeDiaryEntry: (id: string, payload: { date: string; body: string }) =>
    request<DiaryEntry>(`/cases/${id}/diary`, { method: "POST", body: JSON.stringify(payload) }),
  deleteDiaryEntry: (id: string, entryId: string) =>
    request<void>(`/cases/${id}/diary/${entryId}`, { method: "DELETE" }),

  tasks: (id: string, includeDone = false) =>
    request<Task[]>(`/cases/${id}/tasks${includeDone ? "?include_done=true" : ""}`),
  addTask: (
    id: string,
    payload: {
      title: string;
      assignee_id: string;
      due_date?: string | null;
      due_before_next_hearing?: boolean;
      diary_entry_id?: string | null;
    },
  ) => request<Task>(`/cases/${id}/tasks`, { method: "POST", body: JSON.stringify(payload) }),
  updateTask: (
    id: string,
    taskId: string,
    payload: {
      title?: string;
      assignee_id?: string;
      due_date?: string | null;
      due_before_next_hearing?: boolean;
      done?: boolean;
    },
  ) =>
    request<Task>(`/cases/${id}/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteTask: (id: string, taskId: string) =>
    request<void>(`/cases/${id}/tasks/${taskId}`, { method: "DELETE" }),

  search: (params: { q: string; firm_status?: FirmStatus; mine?: boolean }) => {
    const qs = new URLSearchParams({ q: params.q });
    if (params.firm_status) qs.set("firm_status", params.firm_status);
    if (params.mine) qs.set("mine", "true");
    return request<SearchHit[]>(`/search?${qs.toString()}`);
  },
  dashboard: () => request<Dashboard>("/dashboard"),

  notes: (id: string) => request<InternalNote[]>(`/cases/${id}/notes`),
  addNote: (id: string, body: string) =>
    request<InternalNote>(`/cases/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  deleteNote: (id: string, noteId: string) =>
    request<void>(`/cases/${id}/notes/${noteId}`, { method: "DELETE" }),
};

export type SearchMode = "cnr" | "case_number" | "filing_number";

export interface StartOut {
  session_id: string;
  districts: string[];
}
export interface ChooseCourtOut {
  state: string;
  district: string;
  court: string;
  case_types: string[];
  known_court_id: string | null;
  known_court_name: string | null;
}
export interface CaptchaOut {
  /** An inline data: URI, read off the portal and shown to a person. */
  captcha: string;
  duplicate_case_id: string | null;
}
export interface PortalParty {
  name: string;
  advocate_name: string | null;
  advocate_registration: string | null;
}

/** What `extract_case` read out of a Snapshot. Read-only - none of it is ours
 *  to edit, only to decide what to do with (ADR-0002). */
export interface PortalCase {
  cino: string;
  case_type: string | null;
  registration_number: string | null;
  registration_date: string | null;
  filing_number: string | null;
  filing_date: string | null;
  court_status: string | null;
  subject: string | null;
  petitioner: PortalParty | null;
  respondent: PortalParty | null;
  /** Individuals the lead name's "and N Others"/"and ANOTHER" stands in for -
   *  real people, each needing their own review (ADR-0005), same as the lead. */
  petitioner_others: PortalParty[];
  respondent_others: PortalParty[];
  first_hearing: string | null;
  next_hearing: string | null;
  last_hearing: string | null;
}

export interface SubmitOut {
  snapshot_id: string;
  raw_length: number;
  raw_preview: string;
  parsed: Record<string, unknown> | null;
  parse_error: string | null;
  extracted: PortalCase | null;
  duplicate_case_id: string | null;
}

export const ingest = {
  start: () => request<StartOut>("/ingest/start", { method: "POST" }),
  district: (sid: string, district: string) =>
    request<{ courts: string[] }>(`/ingest/${sid}/district`, {
      method: "POST",
      body: JSON.stringify({ district }),
    }),
  court: (sid: string, court: string) =>
    request<ChooseCourtOut>(`/ingest/${sid}/court`, {
      method: "POST",
      body: JSON.stringify({ court }),
    }),
  identifier: (
    sid: string,
    payload: { mode: SearchMode; value: string; case_type?: string | null; year?: string | null },
  ) =>
    request<CaptchaOut>(`/ingest/${sid}/identifier`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  captcha: (sid: string) => request<CaptchaOut>(`/ingest/${sid}/captcha`),
  submit: (sid: string, captcha: string) =>
    request<SubmitOut>(`/ingest/${sid}/submit`, {
      method: "POST",
      body: JSON.stringify({ captcha }),
    }),
  cancel: (sid: string) => request<void>(`/ingest/${sid}`, { method: "DELETE" }),
  review: (sid: string, payload: unknown) =>
    request<CaseDetail>(`/ingest/${sid}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/** One court-sourced field a Snapshot would change. Already rendered as text:
 *  a diff screen compares values, it does not compute with them. */
export interface FieldChange {
  field: string;
  label: string;
  before: string | null;
  after: string | null;
}

export interface HearingFace {
  state: HearingState;
  source: HearingSource;
  purpose: string | null;
  outcome: string | null;
  presiding_officer: string | null;
  order_available: boolean;
}

export interface HearingChange {
  date: string;
  change: "new" | "changed" | "superseded";
  /** The court's account is about to stand over one the firm wrote down
   *  (ADR-0002). Worth saying out loud rather than letting it happen quietly. */
  takes_over_firm_record: boolean;
  before: HearingFace | null;
  after: HearingFace;
}

/** A block replaced wholesale — Act & Section, or one party's Counsel. */
export interface ListChange {
  label: string;
  before: string[];
  after: string[];
}

export type SnapshotStatus = "captured" | "applied" | "rejected" | "superseded";

/** Everything applying this Snapshot would do. Shown whole, applied whole,
 *  or discarded whole — never picked over field by field (rule 2, ADR-0007). */
export interface RefreshDiff {
  snapshot_id: string;
  case_id: string;
  status: SnapshotStatus;
  fetched_at: string;
  found: boolean;
  cino: string | null;
  cino_mismatch: boolean;
  parse_error: string | null;
  raw_preview: string;
  fields: FieldChange[];
  hearings: HearingChange[];
  act_sections: ListChange | null;
  crime_details: FieldChange[];
  counsel: ListChange[];
  /** Names the portal reports that no Party here is linked to. A refresh never
   *  links one — that is a person's judgement (ADR-0005). */
  unlinked_parties: string[];
  /** Dates the firm has on record that the court says nothing about. Left
   *  exactly alone. */
  firm_dates_not_reported: string[];
  has_changes: boolean;
}

export interface RefreshStart {
  session_id: string;
  captcha: string;
  cino: string;
  state: string;
  district: string;
  court: string;
}

export interface SnapshotSummary {
  id: string;
  status: SnapshotStatus;
  fetched_at: string;
  decided_at: string | null;
  search_mode: string;
  search_value: string;
  parse_error: string | null;
}

export const refresh = {
  start: (caseId: string) => request<RefreshStart>(`/cases/${caseId}/refresh`, { method: "POST" }),
  captcha: (caseId: string, sid: string) =>
    request<CaptchaOut>(`/cases/${caseId}/refresh/${sid}/captcha`),
  submit: (caseId: string, sid: string, captcha: string) =>
    request<RefreshDiff>(`/cases/${caseId}/refresh/${sid}/submit`, {
      method: "POST",
      body: JSON.stringify({ captcha }),
    }),
  cancel: (caseId: string, sid: string) =>
    request<void>(`/cases/${caseId}/refresh/${sid}`, { method: "DELETE" }),

  snapshots: (caseId: string) => request<SnapshotSummary[]>(`/cases/${caseId}/snapshots`),
  diff: (caseId: string, snapshotId: string) =>
    request<RefreshDiff>(`/cases/${caseId}/snapshots/${snapshotId}/diff`),
  apply: (caseId: string, snapshotId: string) =>
    request<CaseDetail>(`/cases/${caseId}/snapshots/${snapshotId}/apply`, { method: "POST" }),
  discard: (caseId: string, snapshotId: string) =>
    request<SnapshotSummary>(`/cases/${caseId}/snapshots/${snapshotId}/discard`, {
      method: "POST",
    }),
};

export const HEARING_STATE_LABEL: Record<HearingState, string> = {
  scheduled: "Scheduled",
  held: "Held",
  superseded: "Superseded",
  unrecorded: "Nothing recorded",
};

/** Dates are days, not moments. Parsing as UTC avoids a timezone shifting a
 *  hearing to the day before. */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function isPast(iso: string): boolean {
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
    today.getDate(),
  ).padStart(2, "0")}`;
  return iso < todayIso;
}

/** How a case is referred to in conversation, falling back as numbers arrive. */
export function caseLabel(c: CaseSummary): string {
  if (c.registration_number) return c.registration_number;
  if (c.filing_number) return `Filing ${c.filing_number}`;
  if (c.cino) return c.cino;
  return "Unnumbered";
}

/** The cause-title form of one side: the lead party's name, plus how many
 *  more there are. For a portal-ingested side, position 1's own name already
 *  is the court's cause-title string ("Rekha Devi P S and 2 Others") and the
 *  rest are the individuals that phrase stands for - not more names to add
 *  here. Only a hand-entered side (no portal_raw_name) has genuinely distinct
 *  parties worth counting separately. */
function sideLabel(parties: CaseParty[], role: PartyRole): string {
  const side = parties.filter((p) => p.role === role).sort((a, b) => a.position - b.position);
  if (side.length === 0) return "—";
  const [lead, ...rest] = side;
  if (lead.portal_raw_name !== null || rest.length === 0) return lead.party.name;
  return `${lead.party.name} and ${rest.length} other${rest.length > 1 ? "s" : ""}`;
}

export function clientsOf(c: CaseSummary): string {
  return sideLabel(c.parties, "client");
}

export function opponentsOf(c: CaseSummary): string {
  return sideLabel(c.parties, "opposite_party");
}

export const FIRM_STATUS_LABEL: Record<FirmStatus, string> = {
  active: "Active",
  on_hold: "On hold",
  relinquished: "Relinquished",
  closed: "Closed",
};

export const ADVOCATE_ROLE_LABEL: Record<AdvocateRole, string> = {
  lead: "Lead",
  assisting: "Assisting",
  appearing: "Appearing",
};
