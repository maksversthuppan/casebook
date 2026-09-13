"use client";

import { useEffect, useState } from "react";

import { inputClass } from "@/app/components/Chrome";
import { api, type Court } from "@/lib/api";

/** A text-searchable court filter for the case list. Search-only - there is
 *  nothing to create here, only to narrow to a court the firm already has
 *  (CONTEXT.md, "Court": only courts the firm actually appears in exist at
 *  all, so there is no wider list to browse). */
export function CourtFilter({
  value,
  onChange,
}: {
  value: Court | null;
  onChange: (court: Court | null) => void;
}) {
  const [term, setTerm] = useState("");
  const [matches, setMatches] = useState<Court[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const query = term.trim();
    // Nothing to search for. Stale matches are harmless - the list below only
    // renders while there is a term to show them against.
    if (!query || value) return;

    let cancelled = false;
    const t = setTimeout(() => {
      api
        .courts(query)
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
      <span className="flex items-center gap-2 text-[0.8125rem] text-ink-soft">
        <span className="text-ink">{value.name}</span>
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
      </span>
    );
  }

  return (
    <div className="relative w-48">
      <input
        className={`${inputClass} w-full py-1 text-[0.75rem]`}
        placeholder="Filter by court…"
        aria-label="Filter by court"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && term.trim() && matches.length > 0 && (
        <ul
          className="absolute z-30 mt-1 w-full overflow-hidden border border-rule-strong bg-leaf text-[0.8125rem]"
          style={{ boxShadow: "3px 3px 0 var(--rule)" }}
        >
          {matches.map((c) => (
            <li key={c.id} className="border-b border-rule last:border-0">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left hover:bg-paper"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange(c);
                  setTerm("");
                }}
              >
                {c.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
