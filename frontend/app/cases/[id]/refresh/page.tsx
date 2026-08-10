"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  Banner,
  Chrome,
  Field,
  PageHead,
  Provenance,
  Sheet,
  inputClass,
} from "@/app/components/Chrome";
import {
  HEARING_STATE_LABEL,
  api,
  caseLabel,
  formatDate,
  refresh,
  type CaseDetail,
  type FieldChange,
  type HearingChange,
  type ListChange,
  type RefreshDiff,
  type RefreshStart,
} from "@/lib/api";

type Step = "captcha" | "diff" | "done";

/** A before/after pair, read as a sentence rather than a table row. What is
 *  arriving is the court's, so it arrives in the court's colour. */
function Change({ before, after }: { before: string | null; after: string | null }) {
  return (
    <span>
      <span className="text-ink-faint line-through">{before ?? "—"}</span>
      <span className="mx-2 text-ink-faint">→</span>
      <strong className="font-medium text-court">{after ?? "—"}</strong>
    </span>
  );
}

function Fields({ title, changes }: { title: string; changes: FieldChange[] }) {
  if (changes.length === 0) return null;
  return (
    <Sheet title={title}>
      <dl>
        {changes.map((c) => (
          <div
            key={c.field}
            className="flex flex-wrap gap-x-4 border-b border-rule py-1.5 last:border-0"
          >
            <dt className="label w-40 shrink-0 pt-0.5">{c.label}</dt>
            <dd className="min-w-0 flex-1 text-[0.8125rem]">
              <Change before={c.before} after={c.after} />
            </dd>
          </div>
        ))}
      </dl>
    </Sheet>
  );
}

function Lists({ title, changes }: { title: string; changes: ListChange[] }) {
  if (changes.length === 0) return null;
  return (
    <Sheet title={title} hint="Replaced as a block, never merged one at a time.">
      <div className="space-y-3">
        {changes.map((c) => (
          <div key={c.label}>
            <p className="label">{c.label}</p>
            <p className="mt-1 text-[0.8125rem]">
              <Change before={c.before.join(", ") || null} after={c.after.join(", ") || null} />
            </p>
          </div>
        ))}
      </div>
    </Sheet>
  );
}

const CHANGE_LABEL: Record<HearingChange["change"], string> = {
  new: "New date",
  changed: "Changed",
  superseded: "No longer listed",
};

function Hearings({ changes }: { changes: HearingChange[] }) {
  if (changes.length === 0) return null;
  return (
    <Sheet title="Hearings">
      <ul className="space-y-5">
        {changes.map((h) => (
          <li key={h.date} className="flex gap-4">
            <time dateTime={h.date} className="ident w-[5.5rem] shrink-0 pt-px text-[0.75rem]">
              {formatDate(h.date)}
            </time>
            <div className="from-court min-w-0 flex-1 pl-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className="label text-ink">{CHANGE_LABEL[h.change]}</span>
                <span className="border border-rule px-1.5 py-px text-[0.6875rem] leading-tight text-ink-soft">
                  {HEARING_STATE_LABEL[h.after.state]}
                </span>
                {h.after.order_available && (
                  <span className="text-[0.6875rem] text-court">Order available</span>
                )}
              </div>

              {h.takes_over_firm_record && (
                <p className="mt-1.5 text-[0.75rem] text-caution">
                  The firm recorded this date. The court&rsquo;s account will stand over it.
                </p>
              )}

              {h.after.purpose && (
                <p className="mt-1.5 text-[0.8125rem]">
                  <span className="label mr-1.5">Purpose</span>
                  {h.after.purpose}
                </p>
              )}
              {h.after.outcome && (
                <p className="mt-1 text-[0.8125rem]">
                  <span className="label mr-1.5">Outcome</span>
                  {h.after.outcome}
                </p>
              )}
              {h.after.presiding_officer && (
                <p className="mt-1 text-[0.75rem] text-ink-soft">
                  Before <span className="font-display italic">{h.after.presiding_officer}</span>
                </p>
              )}
              {h.before && (h.before.purpose || h.before.outcome) && (
                <p className="mt-1.5 text-[0.75rem] text-ink-faint line-through">
                  {h.before.purpose ?? "—"}
                  {h.before.outcome ? ` · ${h.before.outcome}` : ""}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

export default function RefreshPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [c, setCase] = useState<CaseDetail | null>(null);
  const [started, setStarted] = useState<RefreshStart | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [diff, setDiff] = useState<RefreshDiff | null>(null);
  const [step, setStep] = useState<Step>("captcha");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A live browser sits on the server until the search is submitted. Leaving
  // the page without saying so would strand it until the sweeper notices.
  const openSession = useRef<string | null>(null);
  useEffect(() => {
    return () => {
      if (openSession.current) void refresh.cancel(id, openSession.current);
    };
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    api.case(id).then((data) => {
      if (!cancelled) setCase(data);
    });
    refresh
      .start(id)
      .then((out) => {
        if (cancelled) {
          void refresh.cancel(id, out.session_id);
          return;
        }
        openSession.current = out.session_id;
        setStarted(out);
        setCaptcha(out.captcha);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not reach the portal");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function reread() {
    if (!started) return;
    try {
      setCaptcha((await refresh.captcha(id, started.session_id)).captcha);
      setCode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not re-read the CAPTCHA");
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!started) return;
    setBusy(true);
    setError(null);
    try {
      const out = await refresh.submit(id, started.session_id, code);
      // The browser is closed the moment the response is stored; deciding
      // needs the Snapshot, not the session.
      openSession.current = null;
      setDiff(out);
      setStep("diff");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The search did not come back");
    } finally {
      setBusy(false);
    }
  }

  async function decide(action: "apply" | "discard") {
    if (!diff) return;
    setBusy(true);
    setError(null);
    try {
      if (action === "apply") {
        await refresh.apply(id, diff.snapshot_id);
        router.push(`/cases/${id}`);
        return;
      }
      await refresh.discard(id, diff.snapshot_id);
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record that decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Chrome>
      <div className="max-w-3xl">
        <PageHead
          eyebrow={
            <Link href={`/cases/${id}`} className="label hover:text-firm">
              ← Back to the case
            </Link>
          }
          title={
            <>
              Refresh <span className="ident text-[1.4rem]">{c ? caseLabel(c) : "this case"}</span>{" "}
              from DCMS
            </>
          }
        >
          {started && (
            <p className="mt-2.5 text-[0.8125rem] text-ink-soft">
              {started.district} · {started.court} · CNR{" "}
              <span className="ident text-ink">{started.cino}</span>
            </p>
          )}
        </PageHead>

        {error && (
          <div className="mb-6 max-w-2xl">
            <Banner kind="error">{error}</Banner>
          </div>
        )}

        {step === "captcha" && (
          <section className="rise rise-2 max-w-xl space-y-5">
            {!started && !error ? (
              <p className="label animate-pulse">
                Opening the portal, selecting the court, filling in the CNR
              </p>
            ) : null}

            {captcha && (
              /* The one step a machine is never allowed to take (ADR-0003). */
              <form onSubmit={search} className="border border-rule-strong bg-leaf p-6">
                <Provenance from="court">The portal asks</Provenance>
                <p className="mt-2 max-w-md text-[0.8125rem] leading-relaxed text-ink-soft">
                  Everything else is filled in. The portal replaces this image about every thirty
                  seconds, so read it now.
                </p>

                <div className="mt-4 flex flex-wrap items-center gap-4">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={captcha}
                    alt="CAPTCHA from the DCMS portal"
                    className="h-12 w-auto border border-rule bg-white p-1"
                    width={150}
                    height={36}
                  />
                  <button type="button" onClick={() => void reread()} className="btn btn-quiet">
                    New image
                  </button>
                </div>

                <div className="mt-5 border-t border-rule pt-5">
                  <Field label="Type what you see">
                    <input
                      className={`${inputClass} ident max-w-48 text-[1.1rem] uppercase tracking-[0.2em]`}
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      autoFocus
                      required
                    />
                  </Field>
                </div>

                <button disabled={busy} className="btn btn-primary mt-5">
                  {busy ? "Searching…" : "Ask DCMS"}
                </button>
              </form>
            )}
          </section>
        )}

        {step === "diff" && diff && (
          <section className="rise rise-2 max-w-3xl space-y-8">
            <div className="space-y-3">
              {!diff.found && (
                <Banner kind="error">
                  The portal matched nothing for this CNR. The snapshot is kept either way; there is
                  nothing to apply.
                </Banner>
              )}
              {diff.cino_mismatch && (
                <Banner kind="error">
                  The portal answered about {diff.cino}, which is not this case. It cannot be
                  applied here.
                </Banner>
              )}
              {diff.parse_error && (
                <Banner kind="error">Could not decode the response: {diff.parse_error}</Banner>
              )}

              {diff.found && !diff.cino_mismatch && !diff.has_changes && (
                <Banner kind="note">
                  Nothing at the court has changed since the last look. Applying still records that
                  this case was confirmed with DCMS today.
                </Banner>
              )}

              {diff.has_changes && (
                <Banner kind="court">
                  Everything below is applied together or not at all — a case never holds half of
                  what the portal said.
                </Banner>
              )}
            </div>

            <Fields title="The case" changes={diff.fields} />
            <Hearings changes={diff.hearings} />
            <Lists title="Acts & Section" changes={diff.act_sections ? [diff.act_sections] : []} />
            <Fields title="Crime Details" changes={diff.crime_details} />
            <Lists title="Counsel" changes={diff.counsel} />

            {(diff.firm_dates_not_reported.length > 0 || diff.unlinked_parties.length > 0) && (
              <div className="space-y-3">
                {/* Both of these are things the refresh is deliberately not doing. */}
                {diff.firm_dates_not_reported.length > 0 && (
                  <Banner kind="note">
                    The firm has {diff.firm_dates_not_reported.map(formatDate).join(", ")} on record
                    and the court says nothing about{" "}
                    {diff.firm_dates_not_reported.length > 1 ? "them" : "it"}. Left exactly as
                    recorded — the portal is often behind what was announced in court.
                  </Banner>
                )}

                {diff.unlinked_parties.length > 0 && (
                  <Banner kind="note">
                    The portal names {diff.unlinked_parties.join(", ")}, who no party on this case
                    is linked to. A refresh never links anyone; add them by hand if they belong
                    here.
                  </Banner>
                )}
              </div>
            )}

            {!diff.found && (
              <details className="border-t border-rule-strong pt-3">
                <summary className="label cursor-pointer text-ink">What came back</summary>
                <pre className="ident mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all bg-sunk p-3 text-[0.6875rem] leading-relaxed">
                  {diff.raw_preview}
                </pre>
              </details>
            )}

            {/* Two buttons and no third. There is no per-field control here and
              there never will be (rule 2, ADR-0007). */}
            <div className="border-t-2 border-ink pt-4">
              <p className="label text-ink">The decision</p>
              <p className="mt-2 max-w-xl text-[0.8125rem] leading-relaxed text-ink-soft">
                A snapshot is taken whole or left alone. Applying replaces every court-sourced fact
                on this case and touches nothing the firm wrote.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  disabled={busy || !diff.found || diff.cino_mismatch}
                  onClick={() => void decide("apply")}
                  className="btn btn-primary"
                >
                  {busy ? "Applying…" : "Apply all"}
                </button>
                <button
                  disabled={busy}
                  onClick={() => void decide("discard")}
                  className="btn btn-quiet"
                >
                  Discard
                </button>
              </div>
              <p className="mt-3 text-[0.75rem] text-ink-faint">
                A discarded snapshot is kept and marked rejected. Somebody solved a CAPTCHA for it.
              </p>
            </div>
          </section>
        )}

        {step === "done" && (
          <section className="rise rise-2 max-w-xl space-y-5">
            <Banner kind="note">
              Discarded. The snapshot is kept against the case, marked rejected, and nothing on the
              case has changed.
            </Banner>
            <Link href={`/cases/${id}`} className="btn btn-quiet">
              Back to the case
            </Link>
          </section>
        )}
      </div>
    </Chrome>
  );
}
