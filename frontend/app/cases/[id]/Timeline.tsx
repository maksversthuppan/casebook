"use client";

import { useEffect, useState } from "react";

import {
  Banner,
  Disclosure,
  Empty,
  Field,
  Provenance,
  Sheet,
  Waiting,
  inputClass,
} from "@/app/components/Chrome";
import {
  HEARING_STATE_LABEL,
  api,
  formatDate,
  isPast,
  type Advocate,
  type Clerk,
  type Hearing,
  type HearingState,
  type TimelineItem,
} from "@/lib/api";

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

const STATE_TONE: Record<HearingState, string> = {
  scheduled: "border-rule-strong text-ink",
  held: "border-rule text-ink-soft",
  superseded: "border-rule text-ink-faint line-through",
  unrecorded: "border-caution text-caution",
};

/** Who is on record as having represented the firm at this Hearing - an
 *  Advocate or a Clerk, entered by a person regardless of whether the Hearing
 *  itself came from the court (CONTEXT.md, "Representation"). */
function RepresentationControl({
  h,
  caseId,
  advocates,
  clerks,
  onClerkCreated,
  onChanged,
}: {
  h: Hearing;
  caseId: string;
  advocates: Advocate[];
  clerks: Clerk[];
  onClerkCreated: (clerk: Clerk) => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [addingClerk, setAddingClerk] = useState(false);
  const [newClerkName, setNewClerkName] = useState("");

  const current = h.represented_by_advocate
    ? `advocate:${h.represented_by_advocate.id}`
    : h.represented_by_clerk
      ? `clerk:${h.represented_by_clerk.id}`
      : "";

  async function apply(selected: string) {
    if (selected === "__new_clerk__") {
      setAddingClerk(true);
      return;
    }
    setBusy(true);
    try {
      const [kind, id] = selected.split(":");
      await api.setRepresentation(caseId, h.id, {
        advocate_id: kind === "advocate" ? id : null,
        clerk_id: kind === "clerk" ? id : null,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function addClerk(e: React.FormEvent) {
    e.preventDefault();
    const name = newClerkName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const clerk = await api.createClerk(name);
      onClerkCreated(clerk);
      await api.setRepresentation(caseId, h.id, {
        advocate_id: null,
        clerk_id: clerk.id,
      });
      setNewClerkName("");
      setAddingClerk(false);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  if (addingClerk) {
    return (
      <form onSubmit={addClerk} className="mt-2.5 flex flex-wrap items-center gap-2">
        <input
          autoFocus
          className={`${inputClass} max-w-52`}
          placeholder="Clerk's name"
          value={newClerkName}
          onChange={(e) => setNewClerkName(e.target.value)}
        />
        <button disabled={busy} className="btn btn-quiet">
          Add
        </button>
        <button type="button" onClick={() => setAddingClerk(false)} className="btn-plain">
          cancel
        </button>
      </form>
    );
  }

  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      <span className="label">Represented by</span>
      <select
        disabled={busy}
        value={current}
        onChange={(e) => apply(e.target.value)}
        aria-label="Who represented the firm at this hearing"
        className="field-input w-auto py-1 text-[0.75rem]"
      >
        <option value="">— not recorded —</option>
        <optgroup label="Advocates">
          {advocates.map((a) => (
            <option key={a.id} value={`advocate:${a.id}`}>
              {a.name}
            </option>
          ))}
        </optgroup>
        {clerks.length > 0 && (
          <optgroup label="Clerks">
            {clerks.map((cl) => (
              <option key={cl.id} value={`clerk:${cl.id}`}>
                {cl.name}
              </option>
            ))}
          </optgroup>
        )}
        <option value="__new_clerk__">+ New clerk…</option>
      </select>
    </div>
  );
}

/** Where the court's account and the advocate's own account are visibly
 *  different things. Two records on one date are normal here, not a duplicate. */
function HearingCard({
  h,
  onChanged,
  caseId,
  advocates,
  clerks,
  onClerkCreated,
}: {
  h: Hearing;
  caseId: string;
  advocates: Advocate[];
  clerks: Clerk[];
  onClerkCreated: (clerk: Clerk) => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const fromCourt = h.source === "court";
  const overdue = h.state === "scheduled" && isPast(h.date);

  async function setState(state: HearingState) {
    setBusy(true);
    try {
      await api.amendHearing(caseId, h.id, { state });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`pl-4 ${fromCourt ? "from-court" : "from-firm"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="label text-ink">Hearing</span>
        <span
          className={`border px-1.5 py-px text-[0.6875rem] leading-tight ${STATE_TONE[h.state]}`}
        >
          {HEARING_STATE_LABEL[h.state]}
        </span>
        <Provenance from={fromCourt ? "court" : "firm"}>
          {fromCourt ? "reported by DCMS" : `noted by ${h.recorded_by?.name ?? "the firm"}`}
        </Provenance>
        {h.order_available && (
          <span className="text-[0.6875rem] text-court">order available on the portal</span>
        )}
      </div>

      {h.purpose && <p className="mt-1.5 text-[0.8125rem]">{h.purpose}</p>}
      {h.outcome && <p className="mt-1 text-[0.8125rem] text-ink-soft">{h.outcome}</p>}
      {h.presiding_officer && (
        <p className="mt-1 text-[0.75rem] text-ink-soft">
          Before <span className="font-display italic">{h.presiding_officer}</span>
        </p>
      )}

      <RepresentationControl
        h={h}
        caseId={caseId}
        advocates={advocates}
        clerks={clerks}
        onClerkCreated={onClerkCreated}
        onChanged={onChanged}
      />

      {overdue && (
        <p className="mt-2 text-[0.75rem] text-caution">
          This date has passed with nothing recorded against it.
        </p>
      )}

      {!fromCourt && h.state === "scheduled" && (
        <div className="mt-2.5 flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => setState("held")} className="btn btn-quiet">
            Mark held
          </button>
          <button disabled={busy} onClick={() => setState("superseded")} className="btn btn-quiet">
            Date was moved
          </button>
        </div>
      )}
    </div>
  );
}

export function Timeline({ caseId, onCaseChanged }: { caseId: string; onCaseChanged: () => void }) {
  const [items, setItems] = useState<TimelineItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [advocates, setAdvocates] = useState<Advocate[]>([]);
  const [clerks, setClerks] = useState<Clerk[]>([]);
  const [me, setMe] = useState<Advocate | null>(null);

  useEffect(() => {
    api
      .advocates()
      .then(setAdvocates)
      .catch(() => setAdvocates([]));
    api
      .clerks()
      .then(setClerks)
      .catch(() => setClerks([]));
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  const [hearingOpen, setHearingOpen] = useState(false);
  const [hearingDate, setHearingDate] = useState(todayIso());
  const [hearingPurpose, setHearingPurpose] = useState("");
  const [entryOpen, setEntryOpen] = useState(false);
  const [entryDate, setEntryDate] = useState(todayIso());
  const [entryBody, setEntryBody] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .timeline(caseId)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load the timeline");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, reloadKey]);

  function refresh() {
    setReloadKey((k) => k + 1);
    onCaseChanged();
  }

  async function addHearing(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.recordHearing(caseId, {
        date: hearingDate,
        purpose: hearingPurpose || null,
      });
      setHearingPurpose("");
      setHearingOpen(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the hearing");
    } finally {
      setBusy(false);
    }
  }

  async function addEntry(e: React.FormEvent) {
    e.preventDefault();
    if (!entryBody.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.writeDiaryEntry(caseId, {
        date: entryDate,
        body: entryBody.trim(),
      });
      setEntryBody("");
      setEntryOpen(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the entry");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      className="rise rise-4"
      title="Timeline"
      /* Deliberately does not name a colour: the palette can move, and a hint
         that says "blue" silently inverts the one distinction that matters. */
      hint="What the court did and what the advocates wrote, in one reading order. A hearing and a diary entry on the same date are two records, not a duplicate. Anything marked as reported by DCMS is the court's own account — refresh the case to take a newer version of it."
    >
      {error && (
        <div className="mb-4">
          <Banner kind="error">{error}</Banner>
        </div>
      )}

      {/* Both slips are the firm writing something down, so both carry the
          firm's rule. */}
      <div className="mb-8 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <form onSubmit={addHearing} className="from-firm pl-4">
          <Disclosure
            label="Record a hearing date"
            hint="The date the judge gave in court, before the portal shows it."
            open={hearingOpen}
            onOpenChange={setHearingOpen}
          >
            <Field label="Date">
              <input
                type="date"
                className={`${inputClass} ident`}
                value={hearingDate}
                onChange={(e) => setHearingDate(e.target.value)}
                required
              />
            </Field>
            <Field label="Purpose">
              <input
                className={inputClass}
                value={hearingPurpose}
                onChange={(e) => setHearingPurpose(e.target.value)}
                placeholder="for written statement"
              />
            </Field>
            <button disabled={busy} className="btn btn-primary">
              Add hearing
            </button>
          </Disclosure>
        </form>

        <form onSubmit={addEntry} className="from-firm pl-4">
          <Disclosure
            label="Write a diary entry"
            hint="Any day, hearing or not. Only you can edit your own entries."
            open={entryOpen}
            onOpenChange={setEntryOpen}
          >
            <Field label="Date">
              <input
                type="date"
                className={`${inputClass} ident`}
                value={entryDate}
                onChange={(e) => setEntryDate(e.target.value)}
                required
              />
            </Field>
            <Field label="What happened">
              <textarea
                className={`${inputClass} hand min-h-24 text-[0.9375rem]`}
                value={entryBody}
                onChange={(e) => setEntryBody(e.target.value)}
                placeholder="Opposite counsel sought time again — third adjournment…"
              />
            </Field>
            <button disabled={busy} className="btn btn-primary">
              Save entry
            </button>
          </Disclosure>
        </form>
      </div>

      {items === null ? (
        <Waiting>Reading the file</Waiting>
      ) : items.length === 0 ? (
        <Empty>
          Nothing recorded yet. Add the next hearing date, or write up what happened today.
        </Empty>
      ) : (
        <ol className="space-y-6">
          {items.map((item, i) => {
            const showDate = i === 0 || items[i - 1].date !== item.date;
            return (
              <li
                key={item.kind === "hearing" ? item.hearing.id : item.entry.id}
                className="group flex gap-4"
              >
                {/* The dates run down the margin; the eye follows them, not the
                    records. */}
                <time
                  dateTime={item.date}
                  className={`ident w-[5.5rem] shrink-0 pt-px text-[0.75rem] ${
                    showDate ? "text-ink" : "invisible"
                  }`}
                >
                  {formatDate(item.date)}
                </time>

                <div className="min-w-0 flex-1">
                  {item.kind === "hearing" ? (
                    <HearingCard
                      h={item.hearing}
                      caseId={caseId}
                      onChanged={refresh}
                      advocates={advocates}
                      clerks={clerks}
                      onClerkCreated={(clerk) => setClerks((prev) => [...prev, clerk])}
                    />
                  ) : (
                    <div className="from-firm pl-4">
                      <div className="flex flex-wrap items-center gap-x-3">
                        <span className="label text-ink">Diary</span>
                        <Provenance from="firm">{item.entry.author.name}</Provenance>
                        {item.entry.author.id === me?.id && (
                          <button
                            onClick={async () => {
                              await api.deleteDiaryEntry(caseId, item.entry.id);
                              refresh();
                            }}
                            className="btn-plain ml-auto opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                          >
                            remove
                          </button>
                        )}
                      </div>
                      {/* Writing, set in the reading face. */}
                      <p className="hand mt-1.5 whitespace-pre-wrap">{item.entry.body}</p>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Sheet>
  );
}
