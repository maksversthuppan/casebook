"use client";

import { useEffect, useState } from "react";

import { inputClass } from "@/app/components/Chrome";
import { api, type Party } from "@/lib/api";

export interface PartyChoice {
  party_id?: string;
  new_party?: {
    name: string;
    kind: "person" | "organisation";
    phone?: string | null;
  };
  label: string;
}

/** Search-or-create. Typing a name shows Parties the firm already has, so the
 *  second case against KSEB links to the same KSEB rather than making another
 *  one - which is what keeps "every case against this opponent" answerable. */
export function PartyPicker({
  value,
  onChange,
  initialTerm = "",
}: {
  value: PartyChoice | null;
  onChange: (choice: PartyChoice | null) => void;
  /** Pre-fills the search box - e.g. the name a DCMS Snapshot returned, so the
   *  likely match is already showing rather than making a person retype it. */
  initialTerm?: string;
}) {
  const [term, setTerm] = useState(initialTerm);
  const [matches, setMatches] = useState<Party[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const query = term.trim();
    // Nothing to search for. Stale matches are harmless - the list below only
    // renders while there is a term to show them against.
    if (!query || value) return;

    let cancelled = false;
    const t = setTimeout(() => {
      api
        .parties(query)
        .then((found) => {
          if (!cancelled) setMatches(found);
        })
        .catch(() => {
          if (!cancelled) setMatches([]);
        });
    }, 200);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [term, value]);

  if (value) {
    return (
      <div className="border border-rule bg-leaf px-3 py-2 text-[0.8125rem]">
        <div className="flex items-baseline gap-2">
          <span className="flex-1">{value.label}</span>
          <span className="label text-[0.5625rem]">{value.party_id ? "existing" : "new"}</span>
          <button
            type="button"
            onClick={() => {
              onChange(null);
              setTerm("");
            }}
            className="btn-plain"
          >
            change
          </button>
        </div>

        {/* Only for a party being created here. An existing one already has
            whatever the firm knows, and it is edited on the case view rather
            than overwritten in passing from a picker. */}
        {value.new_party && (
          <input
            className={`${inputClass} ident mt-2 py-1 text-[0.75rem]`}
            value={value.new_party.phone ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                new_party: {
                  ...value.new_party!,
                  phone: e.target.value || null,
                },
              })
            }
            placeholder="Phone (optional)"
          />
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        className={inputClass}
        placeholder="Search or type a new name"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && term.trim() && (
        <ul
          className="absolute z-30 mt-1 w-full overflow-hidden border border-rule-strong bg-leaf text-[0.8125rem]"
          style={{ boxShadow: "3px 3px 0 var(--rule)" }}
        >
          {/* The "add new" options come first and stay first - existing
              matches arrive later over the network (debounced, and often
              already in flight when `initialTerm` pre-fills the box), and
              inserting them above these buttons shifted the list under a
              click already in progress, so the click landed on nothing.

              Defaults to a person - most parties are - with organisation as a
              smaller, explicit second choice rather than two equal-weight
              buttons every time. */}
          <li className="border-b border-rule">
            <button
              type="button"
              className="block w-full px-3 py-2 text-left hover:bg-paper"
              onMouseDown={(e) => {
                e.preventDefault();
                onChange({
                  new_party: { name: term.trim(), kind: "person" },
                  label: term.trim(),
                });
              }}
            >
              Add <strong>{term.trim()}</strong> as a new party
            </button>
          </li>
          <li className="border-b border-rule">
            <button
              type="button"
              className="block w-full px-3 py-1.5 text-left text-[0.75rem] text-ink-soft hover:bg-paper hover:text-ink"
              onMouseDown={(e) => {
                e.preventDefault();
                onChange({
                  new_party: { name: term.trim(), kind: "organisation" },
                  label: term.trim(),
                });
              }}
            >
              …or add as an organisation instead
            </button>
          </li>
          {matches.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="flex w-full items-baseline gap-2 px-3 py-2 text-left hover:bg-paper"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange({ party_id: p.id, label: p.name });
                }}
              >
                <span className="flex-1">{p.name}</span>
                <span className="label text-[0.5625rem]">{p.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
