"use client";

import { useState } from "react";

import { inputClass } from "@/app/components/Chrome";
import { api, type CaseParty } from "@/lib/api";

/** A party's name, what the firm knows about reaching them, and the other
 *  side's lawyer(s) where the portal has any on record.
 *
 *  The phone and the note belong to the Party and travel with them across every
 *  case they appear in. Anything true of one case only is an Internal Note on
 *  that case, not a note on the person (CONTEXT.md, "Party"). */
export function PartyLine({ p, onChanged }: { p: CaseParty; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState(p.party.phone ?? "");
  const [notes, setNotes] = useState(p.party.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.updateParty(p.party.id, {
        phone: phone.trim() || null,
        notes: notes.trim() || null,
      });
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="group mb-2.5 last:mb-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span>{p.party.name}</span>
        {!editing && (
          <button
            onClick={() => {
              setPhone(p.party.phone ?? "");
              setNotes(p.party.notes ?? "");
              setError(null);
              setEditing(true);
            }}
            className={`btn-plain transition-opacity focus-visible:opacity-100 group-hover:opacity-100 ${
              p.party.phone || p.party.notes ? "opacity-0" : "opacity-60"
            }`}
          >
            {p.party.phone || p.party.notes ? "edit" : "add a phone or note"}
          </button>
        )}
      </div>

      {editing ? (
        <div className="mt-1.5 space-y-2">
          <input
            className={`${inputClass} ident`}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Phone (optional)"
          />
          <textarea
            className={`${inputClass} min-h-16`}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="About this person, in every case — 'speaks only Malayalam', 'her son handles everything'"
          />
          <div className="flex gap-2">
            <button onClick={save} disabled={busy} className="btn btn-primary">
              Save
            </button>
            <button onClick={() => setEditing(false)} className="btn btn-quiet">
              Cancel
            </button>
          </div>
          {error && <p className="text-[0.75rem] text-danger">{error}</p>}
        </div>
      ) : (
        <>
          {p.party.phone && (
            <div className="ident text-[0.75rem] text-ink-soft">{p.party.phone}</div>
          )}
          {p.party.notes && (
            <div className="mt-0.5 whitespace-pre-wrap text-[0.75rem] italic leading-relaxed text-ink-soft">
              {p.party.notes}
            </div>
          )}
        </>
      )}

      {/* The other side's lawyer, as the portal names them — never one of us. */}
      {p.counsels.length > 0 && (
        <div className="mt-0.5 text-[0.75rem] text-court">
          <span className="label text-[0.5625rem] text-court">Counsel</span>{" "}
          {p.counsels.map((c) => c.name).join(", ")}
        </div>
      )}
    </div>
  );
}
