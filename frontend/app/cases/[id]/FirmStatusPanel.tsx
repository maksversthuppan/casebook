"use client";

import { useEffect, useState } from "react";

import { FirmStatusTag, Provenance, Sheet, inputClass } from "@/app/components/Chrome";
import {
  FIRM_STATUS_LABEL,
  api,
  type CaseDetail,
  type FirmStatus,
  type FirmStatusChange,
} from "@/lib/api";

const ORDER: FirmStatus[] = ["active", "on_hold", "relinquished", "closed"];

function describe(change: FirmStatusChange): string {
  const to = FIRM_STATUS_LABEL[change.to_status];
  return change.from_status === null
    ? `Opened as ${to.toLowerCase()}`
    : `${FIRM_STATUS_LABEL[change.from_status]} → ${to}`;
}

/** The firm's own status, and how it got here.
 *
 *  Changing it is deliberately two steps rather than one. A status is not a
 *  toggle - relinquishing a case is a real decision, and the pause is where the
 *  reason gets asked for while whoever made it still remembers. */
export function FirmStatusPanel({
  c,
  onChanged,
}: {
  c: CaseDetail;
  onChanged: (updated: CaseDetail) => void;
}) {
  const [history, setHistory] = useState<FirmStatusChange[] | null>(null);
  const [pending, setPending] = useState<FirmStatus | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .firmStatusHistory(c.id)
      .then((data) => {
        if (!cancelled) setHistory(data);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });
    return () => {
      cancelled = true;
    };
  }, [c.id, reloadKey]);

  async function commit() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      onChanged(
        await api.updateCase(c.id, {
          firm_status: pending,
          firm_status_reason: reason.trim() || null,
        }),
      );
      setPending(null);
      setReason("");
      setReloadKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the status");
    } finally {
      setBusy(false);
    }
  }

  // The opening entry is always there, so a case nobody has touched shows one
  // line rather than an empty panel.
  const latest = history?.[0] ?? null;
  const shown = history === null ? [] : showAll ? history : history.slice(0, 3);

  return (
    <Sheet className="rise rise-3" title="Status">
      {/* The two statuses are kept visibly apart, each under its own voice.
          They legitimately disagree, and reading one for the other is the
          mistake this layout exists to prevent. */}
      <div className="from-firm pl-3.5">
        <Provenance from="firm">The firm</Provenance>

        <div className="mt-2 grid grid-cols-2 gap-px bg-rule">
          {ORDER.map((s) => {
            const current = c.firm_status === s;
            return (
              <button
                key={s}
                onClick={() => {
                  setPending(s === c.firm_status ? null : s);
                  setReason("");
                }}
                aria-pressed={current}
                /* Relinquished fills in danger red wherever it wins, so the one
                   status that has to shout does not look like the other three. */
                className={`px-2 py-1.5 text-[0.75rem] transition-colors ${
                  current
                    ? s === "relinquished"
                      ? "bg-danger font-semibold text-on-accent"
                      : "bg-firm font-semibold text-on-accent"
                    : pending === s
                      ? "bg-firm-wash text-firm ring-1 ring-inset ring-firm"
                      : "bg-paper text-ink-soft hover:bg-leaf hover:text-ink"
                }`}
              >
                {FIRM_STATUS_LABEL[s]}
              </button>
            );
          })}
        </div>

        {pending && (
          /* Giving a case up is the one change here that is hard to walk back,
             so its confirmation is the only one that turns red. */
          <div
            className={`mt-3 border p-2.5 ${
              pending === "relinquished"
                ? "border-danger bg-danger-wash"
                : "border-firm bg-firm-wash"
            }`}
          >
            <p className="text-[0.75rem] leading-relaxed">
              Change to <strong>{FIRM_STATUS_LABEL[pending]}</strong>
              {pending === "relinquished" && (
                <span className="mt-1 block text-ink-soft">
                  The firm is giving this case up. It stays readable and refreshable, and leaves
                  every working list.
                </span>
              )}
            </p>
            <input
              className={`${inputClass} mt-2`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why? (optional)"
            />
            <div className="mt-2 flex gap-2">
              <button onClick={commit} disabled={busy} className="btn btn-primary">
                Save
              </button>
              <button
                onClick={() => {
                  setPending(null);
                  setReason("");
                }}
                className="btn btn-quiet"
              >
                Cancel
              </button>
            </div>
            {error && <p className="mt-2 text-[0.75rem] text-danger">{error}</p>}
          </div>
        )}

        {latest && (
          <p className="mt-2.5 flex flex-wrap items-center gap-x-2 text-[0.75rem] text-ink-soft">
            {c.firm_status === "relinquished" && <FirmStatusTag status="relinquished" />}
            <span>
              Since{" "}
              <span className="ident">
                {new Date(latest.created_at).toLocaleDateString("en-GB")}
              </span>
              {latest.changed_by ? `, ${latest.changed_by.name}` : ""}
              {latest.reason ? ` — ${latest.reason}` : ""}
            </span>
          </p>
        )}
      </div>

      <div className="from-court mt-6 pl-3.5">
        <Provenance from="court">The court</Provenance>
        <p className="mt-1.5 text-[0.9375rem] text-court">
          {c.court_status ?? <span className="italic text-ink-faint">not known</span>}
        </p>
        <p className="mt-1 text-[0.75rem] text-ink-soft">
          {c.last_refreshed_at ? (
            <>
              Confirmed with DCMS on{" "}
              <span className="ident">
                {new Date(c.last_refreshed_at).toLocaleDateString("en-GB")}
              </span>
            </>
          ) : (
            "Never confirmed with DCMS"
          )}
        </p>
      </div>

      {/* Kept off the Timeline on purpose: the Timeline is what the court and
          the advocates did about the case, this is the firm's own bookkeeping
          about it (CONTEXT.md, "Firm Status History"). */}
      {history !== null && history.length > 0 && (
        <div className="mt-6 border-t border-rule pt-3">
          <p className="label">How the firm status got here</p>
          <ul className="mt-2 space-y-2">
            {shown.map((h) => (
              <li key={h.id} className="text-[0.75rem] leading-relaxed">
                <span className="ident text-ink-faint">
                  {new Date(h.created_at).toLocaleDateString("en-GB")}
                </span>{" "}
                {describe(h)}
                <span className="text-ink-soft">
                  {h.changed_by ? ` · ${h.changed_by.name}` : ""}
                </span>
                {h.reason && <span className="block italic text-ink-soft">{h.reason}</span>}
              </li>
            ))}
          </ul>
          {history.length > 3 && (
            <button onClick={() => setShowAll((v) => !v)} className="btn-plain mt-2.5">
              {showAll ? "Show less" : `Show all ${history.length}`}
            </button>
          )}
        </div>
      )}
    </Sheet>
  );
}
