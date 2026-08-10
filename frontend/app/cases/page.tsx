"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Banner, Chrome, FirmStatusTag, PageHead, Waiting } from "@/app/components/Chrome";
import {
  FIRM_STATUS_LABEL,
  api,
  caseLabel,
  clientsOf,
  formatDate,
  isPast,
  opponentsOf,
  type CaseSummary,
  type FirmStatus,
  type SearchMatch,
} from "@/lib/api";

const STATUSES: (FirmStatus | "all")[] = ["active", "on_hold", "relinquished", "closed", "all"];

const MATCH_LABEL: Record<SearchMatch["kind"], string> = {
  identifier: "number",
  party: "party",
  diary: "diary",
  note: "note",
};

/** Why this case came back, so nobody has to open it to find out. The snippet
 *  arrives with the hit wrapped in << >>, which is rendered as a highlight
 *  rather than as punctuation. */
function MatchReason({ matches }: { matches?: SearchMatch[] }) {
  if (!matches?.length) return null;
  return (
    <div className="mt-1 space-y-0.5">
      {matches.map((m, i) => (
        <div key={i} className="text-[0.75rem] leading-snug text-ink-soft">
          <span className="label mr-1.5 text-[0.5625rem] tracking-[0.16em]">
            {MATCH_LABEL[m.kind]}
          </span>
          {m.snippet?.split(/<<|>>/).map((part, j) =>
            j % 2 === 1 ? (
              <mark key={j} className="bg-firm-wash font-semibold text-firm">
                {part}
              </mark>
            ) : (
              <span key={j}>{part}</span>
            ),
          )}
        </div>
      ))}
    </div>
  );
}

function RefreshState({ c }: { c: CaseSummary }) {
  // Three distinct situations, and conflating them would mislead: the court has
  // never been asked, the court cannot be asked yet, or the court was asked on
  // a date. Nothing here is ever "up to date" - only "confirmed on".
  if (!c.court.is_complete) {
    return (
      <span className="italic text-ink-faint" title="Its court has not been identified on DCMS yet">
        court not identified
      </span>
    );
  }
  if (!c.last_refreshed_at) return <span className="italic text-ink-faint">never</span>;
  return (
    <span className="ident text-ink-soft">
      {new Date(c.last_refreshed_at).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })}
    </span>
  );
}

export default function CasesPage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  // Why each case matched, keyed by case id. Empty while browsing rather than
  // searching - there is no "why" for a list nobody filtered.
  const [why, setWhy] = useState<Record<string, SearchMatch[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<FirmStatus | "all">("active");
  const [mine, setMine] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const firm_status = status === "all" ? undefined : status;
      if (q.trim()) {
        // One box over identifiers, the people involved and the firm's own
        // writing. The endpoint says why each case came back.
        const hits = await api.search({ q: q.trim(), firm_status, mine });
        setCases(hits.map((h) => h.case));
        setWhy(Object.fromEntries(hits.map((h) => [h.case.id, h.matches])));
      } else {
        setCases(await api.cases({ firm_status, mine }));
        setWhy({});
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load cases");
    }
  }, [q, status, mine]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  return (
    <Chrome>
      <PageHead
        eyebrow={<span className="label">The register</span>}
        title="Cases"
        action={
          <Link href="/cases/new" className="btn btn-primary">
            Add a case
          </Link>
        }
      />

      {/* The search line reads as a line of writing rather than a widget: no
          box, just a rule under it. */}
      <input
        className="rise rise-2 mb-6 w-full max-w-2xl border-b border-rule-strong bg-transparent pb-1.5 font-display text-[1.05rem] italic outline-none placeholder:text-ink-faint focus:border-firm"
        placeholder="a number, a name, or anything written in the diary…"
        aria-label="Find a case"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="rise rise-2 mb-6 flex flex-wrap items-baseline gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-baseline gap-x-5">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              aria-pressed={status === s}
              className={`label border-b-2 pb-0.5 transition-colors ${
                status === s
                  ? "border-firm text-firm"
                  : "border-transparent hover:border-rule-strong hover:text-ink"
              }`}
            >
              {s === "all" ? "All" : FIRM_STATUS_LABEL[s]}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-[0.8125rem] text-ink-soft">
          <input
            type="checkbox"
            className="accent-[var(--firm)]"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
          />
          Only mine
        </label>

        {cases && (
          <span className="ident ml-auto text-[0.6875rem] text-ink-faint">
            {cases.length} {cases.length === 1 ? "case" : "cases"}
          </span>
        )}
      </div>

      {error && (
        <div className="mb-5">
          <Banner kind="error">{error}</Banner>
        </div>
      )}

      {cases === null ? (
        <Waiting>Turning the pages</Waiting>
      ) : cases.length === 0 ? (
        <Banner kind="note">
          No cases here yet. Cases are normally brought in by finding them on DCMS; until that is
          built, add one by hand.
        </Banner>
      ) : (
        <div className="rise rise-3 overflow-x-auto">
          <table className="w-full border-collapse text-[0.8125rem]">
            <thead>
              <tr className="double-rule [&>th]:whitespace-nowrap [&>th]:py-2 [&>th]:pr-4 [&>th]:text-left">
                <th className="label">Case</th>
                <th className="label">Court</th>
                <th className="label">Parties</th>
                <th className="label">Next hearing</th>
                <th className="label">Firm</th>
                <th className="label">Court says</th>
                <th className="label">Confirmed</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-rule align-baseline transition-colors last:border-0 hover:bg-leaf"
                >
                  <td className="py-2.5 pr-4">
                    <Link
                      href={`/cases/${c.id}`}
                      className="ident font-medium hover:text-firm hover:underline"
                    >
                      {caseLabel(c)}
                    </Link>
                    {c.case_type && (
                      <span className="label ml-2 text-[0.5625rem]">{c.case_type}</span>
                    )}
                    <MatchReason matches={why[c.id]} />
                  </td>
                  <td className="py-2.5 pr-4 text-ink-soft">{c.court.name}</td>
                  {/* The case as it is said out loud: our client, then theirs.
                      Capped by a block child — a max-width on the cell itself
                      is advisory in a table and the text runs into the column
                      beside it. */}
                  <td className="py-2.5 pr-4">
                    <div className="max-w-[20rem]">
                      {clientsOf(c)}
                      <span className="font-display italic text-ink-faint"> v. </span>
                      <span className="text-ink-soft">{opponentsOf(c)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 pr-4">
                    {c.next_hearing_date ? (
                      <span
                        className={`ident ${isPast(c.next_hearing_date) ? "text-caution" : ""}`}
                        title={
                          isPast(c.next_hearing_date)
                            ? "That date has passed with nothing recorded against it"
                            : undefined
                        }
                      >
                        {formatDate(c.next_hearing_date)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4">
                    <FirmStatusTag status={c.firm_status} />
                  </td>
                  <td className="py-2.5 pr-4">
                    {c.court_status ? (
                      <span className="text-court">{c.court_status}</span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>
                  <td className="py-2.5 text-[0.75rem]">
                    <RefreshState c={c} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {cases !== null && cases.length > 0 && (
        <p className="mt-4 text-[0.75rem] text-ink-faint">
          <span className="text-court">Court says</span> is the portal&rsquo;s word and{" "}
          <span className="text-firm">Firm</span> is ours. They legitimately disagree.
        </p>
      )}
    </Chrome>
  );
}
