"use client";

import { useEffect, useState } from "react";

import { inputClass } from "@/app/components/Chrome";
import { api, type Advocate, type CaseDetail } from "@/lib/api";

type Choice = "none" | "advocate" | "outside";

/** Who the firm says is on record in this case.
 *
 *  The firm's own claim, and deliberately not the advocate the portal names for
 *  our side: a vakalath filed on Tuesday is not on the portal on Tuesday, and
 *  one returned may keep showing for weeks. Where the two disagree that is
 *  worth seeing (ADR-0008). Firm-entered, so no refresh ever touches it. */
export function Vakalath({
  c,
  onChanged,
}: {
  c: CaseDetail;
  onChanged: (updated: CaseDetail) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [advocates, setAdvocates] = useState<Advocate[]>([]);
  const [choice, setChoice] = useState<Choice>("none");
  const [advocateId, setAdvocateId] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) return;
    api
      .advocates()
      .then(setAdvocates)
      .catch(() => setAdvocates([]));
  }, [editing]);

  function open() {
    setChoice(c.vakalath_advocate ? "advocate" : c.vakalath_holder_name ? "outside" : "none");
    setAdvocateId(c.vakalath_advocate?.id ?? "");
    setName(c.vakalath_holder_name ?? "");
    setError(null);
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onChanged(
        await api.setVakalath(c.id, {
          advocate_id: choice === "advocate" ? advocateId || null : null,
          holder_name: choice === "outside" ? name.trim() || null : null,
        }),
      );
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the vakalath");
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    const held = c.vakalath_advocate?.name ?? c.vakalath_holder_name;
    return (
      <div className="group flex flex-wrap items-baseline gap-x-2">
        {held ? (
          <span>
            {held}
            {c.vakalath_holder_name && (
              <span className="label ml-2 text-[0.5625rem]">outside the firm</span>
            )}
          </span>
        ) : (
          <span className="text-ink-faint">None recorded</span>
        )}
        <button
          onClick={open}
          className="btn-plain opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
        >
          change
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[0.75rem]">
        {(
          [
            ["none", "None"],
            ["advocate", "One of us"],
            ["outside", "Outside the firm"],
          ] as [Choice, string][]
        ).map(([value, label]) => (
          <label key={value} className="flex items-center gap-1.5">
            <input
              type="radio"
              className="accent-[var(--firm)]"
              checked={choice === value}
              onChange={() => setChoice(value)}
            />
            {label}
          </label>
        ))}
      </div>

      {choice === "advocate" && (
        <select
          className={inputClass}
          value={advocateId}
          onChange={(e) => setAdvocateId(e.target.value)}
          aria-label="Which advocate holds it"
        >
          <option value="">Choose an advocate…</option>
          {advocates.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      )}

      {choice === "outside" && (
        <input
          className={inputClass}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="The advocate we are assisting under"
        />
      )}

      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={busy || (choice === "advocate" && !advocateId)}
          className="btn btn-primary"
        >
          Save
        </button>
        <button onClick={() => setEditing(false)} className="btn btn-quiet">
          Cancel
        </button>
      </div>
      {error && <p className="text-[0.75rem] text-danger">{error}</p>}
    </div>
  );
}
