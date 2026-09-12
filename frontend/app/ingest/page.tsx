"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { PartyPicker, type PartyChoice } from "@/app/cases/new/PartyPicker";
import {
  ADVOCATE_ROLE_LABEL,
  FIRM_STATUS_LABEL,
  api,
  formatDate,
  ingest,
  type Advocate,
  type AdvocateRole,
  type CaptchaOut,
  type ChooseCourtOut,
  type FirmStatus,
  type SearchMode,
  type SubmitOut,
} from "@/lib/api";

type Step = "court" | "identifier" | "captcha" | "review" | "done";

const MODE_LABEL: Record<SearchMode, string> = {
  cnr: "CNR",
  case_number: "Case No",
  filing_number: "Filing No",
};

const STEP_NAME: Record<Step, string> = {
  court: "Court",
  identifier: "Case",
  captcha: "CAPTCHA",
  review: "Review",
  done: "Result",
};

/** The five steps as a numbered sequence on a rule, the way a form is printed. */
function Steps({ step }: { step: Step }) {
  const order: Step[] = ["court", "identifier", "captcha", "review", "done"];
  const at = order.indexOf(step);
  return (
    <ol className="rise rise-2 mb-8 flex flex-wrap items-center gap-x-2.5 gap-y-2">
      {order.map((s, i) => {
        const state = at === i ? "now" : at > i ? "past" : "next";
        return (
          <li key={s} className="flex items-center gap-2.5">
            <span
              className={`flex items-baseline gap-1.5 ${
                state === "now"
                  ? "text-firm"
                  : state === "past"
                    ? "text-ink-soft"
                    : "text-ink-faint"
              }`}
            >
              <span className="ident text-[0.6875rem]">{i + 1}</span>
              <span className="label" style={state === "now" ? { color: "inherit" } : undefined}>
                {STEP_NAME[s]}
              </span>
            </span>
            {i < order.length - 1 && <span className="w-5 border-t border-rule-strong" />}
          </li>
        );
      })}
    </ol>
  );
}

/** One court-reported fact on the review screen. Read-only, and marked as the
 *  court's — none of it is ours to edit (ADR-0002). */
function Reported({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-x-4 border-b border-rule py-1.5 last:border-0">
      <dt className="label w-36 shrink-0 pt-0.5">{label}</dt>
      <dd className="min-w-0 flex-1 text-[0.8125rem]">{children}</dd>
    </div>
  );
}

export default function IngestPage() {
  const router = useRouter();

  const [sid, setSid] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("court");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [districts, setDistricts] = useState<string[]>([]);
  const [district, setDistrict] = useState("");
  const [courts, setCourts] = useState<string[]>([]);
  const [court, setCourt] = useState("");
  const [chosen, setChosen] = useState<ChooseCourtOut | null>(null);

  // Case No is what an advocate normally has in hand when starting from
  // scratch; the CNR is what the portal teaches once a case is found.
  const [mode, setMode] = useState<SearchMode>("case_number");
  const [value, setValue] = useState("");
  const [caseType, setCaseType] = useState("");
  const [year, setYear] = useState("");

  const [captcha, setCaptcha] = useState<CaptchaOut | null>(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState<SubmitOut | null>(null);

  const [me, setMe] = useState<Advocate | null>(null);
  const [reviewAdvocates, setReviewAdvocates] = useState<Advocate[]>([]);
  const [reviewRoles, setReviewRoles] = useState<Record<string, AdvocateRole | "">>({});
  const [clientSide, setClientSide] = useState<"petitioner" | "respondent" | null>(null);
  const [petitionerParty, setPetitionerParty] = useState<PartyChoice | null>(null);
  const [respondentParty, setRespondentParty] = useState<PartyChoice | null>(null);
  // One slot per individual the lead name's "and N Others"/"and ANOTHER"
  // stands in for - each needs its own review, same as the lead (ADR-0005).
  const [petitionerOtherParties, setPetitionerOtherParties] = useState<(PartyChoice | null)[]>([]);
  const [respondentOtherParties, setRespondentOtherParties] = useState<(PartyChoice | null)[]>([]);
  const [firmStatus, setFirmStatus] = useState<FirmStatus>("active");

  const [attempt, setAttempt] = useState(0);
  const sidRef = useRef<string | null>(null);

  // Asked for, not assumed: whether to change the district/court once past
  // the identifier step. Confirmed inline rather than in a popup, the same
  // way Disclosure expands in place instead of a modal.
  const [confirmRestart, setConfirmRestart] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
    api
      .advocates()
      .then(setReviewAdvocates)
      .catch(() => setReviewAdvocates([]));
  }, []);

  // The advocate running the ingestion defaults onto the case as lead, editable
  // from there - mirrors manual case creation's requirement of at least one.
  // Computed at render rather than synced into state via an effect.
  function roleFor(a: Advocate): AdvocateRole | "" {
    return reviewRoles[a.id] ?? (me?.id === a.id ? "lead" : "");
  }

  useEffect(() => {
    sidRef.current = sid;
  }, [sid]);

  // A live browser sits on the server for as long as this page is open. Leaving
  // without saying so would strand it until the sweeper notices.
  useEffect(() => {
    return () => {
      if (sidRef.current) void ingest.cancel(sidRef.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    ingest
      .start()
      .then((out) => {
        if (cancelled) return;
        setSid(out.session_id);
        setDistricts(out.districts);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not reach the portal");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  async function pickDistrict(d: string) {
    if (!sid) return;
    setBusy(true);
    setError(null);
    setDistrict(d);
    setCourt("");
    setCourts([]);
    try {
      setCourts((await ingest.district(sid, d)).courts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load courts");
    } finally {
      setBusy(false);
    }
  }

  async function pickCourt(c: string) {
    if (!sid) return;
    setBusy(true);
    setError(null);
    setCourt(c);
    try {
      const out = await ingest.court(sid, c);
      setChosen(out);
      setStep("identifier");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not select that court");
    } finally {
      setBusy(false);
    }
  }

  async function askForCaptcha(e: React.FormEvent) {
    e.preventDefault();
    if (!sid) return;
    setBusy(true);
    setError(null);
    try {
      const out = await ingest.identifier(sid, {
        mode,
        value,
        case_type: mode === "cnr" ? null : caseType || null,
        year: mode === "cnr" ? null : year || null,
      });
      setCaptcha(out);
      setStep("captcha");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not fill in the search");
    } finally {
      setBusy(false);
    }
  }

  async function reread() {
    if (!sid) return;
    try {
      setCaptcha(await ingest.captcha(sid));
      setCode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not re-read the CAPTCHA");
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!sid) return;
    setBusy(true);
    setError(null);
    try {
      const out = await ingest.submit(sid, code);
      setResult(out);
      setClientSide(null);
      const extracted = out.extracted;
      setPetitionerParty(
        extracted?.petitioner ? defaultPartyChoice(extracted.petitioner.name) : null,
      );
      setRespondentParty(
        extracted?.respondent ? defaultPartyChoice(extracted.respondent.name) : null,
      );
      setPetitionerOtherParties(
        extracted ? extracted.petitioner_others.map((p) => defaultPartyChoice(p.name)) : [],
      );
      setRespondentOtherParties(
        extracted ? extracted.respondent_others.map((p) => defaultPartyChoice(p.name)) : [],
      );
      // A search that found nothing has nothing to review - show it raw, same
      // as a parse failure would, rather than opening an empty review form.
      setStep(out.extracted ? "review" : "done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The search did not come back");
    } finally {
      setBusy(false);
    }
  }

  function partySpec(choice: PartyChoice) {
    return choice.party_id ? { party_id: choice.party_id } : { new_party: choice.new_party };
  }

  // The portal's own name, ready to create as a new Party without an extra
  // click - "change" still reaches the search-or-link picker for whoever
  // isn't a stranger to the firm. Never a silent link to an existing Party:
  // that choice stays the advocate's (ROADMAP, "Party linking", 2026-08-09).
  function defaultPartyChoice(name: string): PartyChoice {
    return { new_party: { name, kind: "person" }, label: name };
  }

  // Changing the district or court once past the identifier step means
  // closing this Playwright session and opening a fresh one - the portal
  // has no "go back" of its own (Findings, 2026-08-05: nothing is
  // searchable before a court is chosen). Anything already searched stays
  // safe regardless: a Snapshot is stored the moment it arrives, before
  // this session is asked to close (rule 3).
  function startOver() {
    if (sid) void ingest.cancel(sid).catch(() => {});
    setSid(null);
    setDistricts([]);
    setDistrict("");
    setCourts([]);
    setCourt("");
    setChosen(null);
    setMode("case_number");
    setValue("");
    setCaseType("");
    setYear("");
    setCaptcha(null);
    setCode("");
    setResult(null);
    setClientSide(null);
    setPetitionerParty(null);
    setRespondentParty(null);
    setPetitionerOtherParties([]);
    setRespondentOtherParties([]);
    setFirmStatus("active");
    setError(null);
    setConfirmRestart(false);
    setStep("court");
    setAttempt((a) => a + 1);
  }

  async function submitReview(e: React.FormEvent) {
    e.preventDefault();
    if (!sid || !result?.extracted) return;
    setError(null);

    const extracted = result.extracted;
    if (extracted.petitioner && !petitionerParty) {
      setError("Link or create a Party for the petitioner.");
      return;
    }
    if (extracted.respondent && !respondentParty) {
      setError("Link or create a Party for the respondent.");
      return;
    }
    if (petitionerOtherParties.some((p) => !p)) {
      setError("Link or create a Party for each additional petitioner.");
      return;
    }
    if (respondentOtherParties.some((p) => !p)) {
      setError("Link or create a Party for each additional respondent.");
      return;
    }
    const assignments = reviewAdvocates
      .map((a) => ({ advocate_id: a.id, role: roleFor(a) }))
      .filter((a) => a.role);
    if (assignments.length === 0) {
      setError("Give at least one advocate a role on this case.");
      return;
    }
    const side = clientSide ?? (extracted.petitioner ? "petitioner" : "respondent");

    setBusy(true);
    try {
      const created = await ingest.review(sid, {
        client_side: side,
        ...(extracted.petitioner ? { petitioner: partySpec(petitionerParty!) } : {}),
        ...(extracted.respondent ? { respondent: partySpec(respondentParty!) } : {}),
        petitioner_others: petitionerOtherParties.map((p) => partySpec(p!)),
        respondent_others: respondentOtherParties.map((p) => partySpec(p!)),
        assignments,
        firm_status: firmStatus,
      });
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the case");
      setBusy(false);
    }
  }

  return (
    <Chrome>
      <div className="max-w-3xl">
        <PageHead
          eyebrow={<span className="label">Ingestion</span>}
          title="Find a case on DCMS"
          lede="The portal will not search anything until a district and court are chosen — not even by CNR. You solve the CAPTCHA; nothing here tries to read it."
        />

        <Steps step={step} />

        {error && (
          <div className="mb-6 max-w-2xl">
            <Banner kind="error">{error}</Banner>
          </div>
        )}

        {confirmRestart && (
          <div className="mb-6 max-w-2xl">
            <Banner kind="caution">
              <p>
                Starting over closes this DCMS session and opens a new one at the district/court
                step — the CAPTCHA and anything typed here is lost.{" "}
                {result
                  ? "The search already made is kept regardless, as a Snapshot, whether or not you come back to it."
                  : "Nothing has been searched yet, so there is nothing else to lose."}
              </p>
              <div className="mt-3 flex gap-3">
                <button onClick={startOver} className="btn btn-quiet">
                  Yes, start over
                </button>
                <button onClick={() => setConfirmRestart(false)} className="btn-plain">
                  Cancel
                </button>
              </div>
            </Banner>
          </div>
        )}

        {step === "court" && (
          <section className="rise rise-3 max-w-2xl space-y-5">
            {!sid && !error ? <p className="label animate-pulse">Opening the portal</p> : null}

            <Field label="District" hint="Straight from the portal's own list.">
              <select
                className={inputClass}
                value={district}
                disabled={busy || !districts.length}
                onChange={(e) => void pickDistrict(e.target.value)}
              >
                <option value="">— choose —</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </Field>

            {courts.length > 0 && (
              <Field label="Court">
                <select
                  className={inputClass}
                  value={court}
                  disabled={busy}
                  onChange={(e) => void pickCourt(e.target.value)}
                >
                  <option value="">— choose —</option>
                  {courts.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            {error && (
              <button
                onClick={() => {
                  setError(null);
                  setAttempt((a) => a + 1);
                }}
                className="btn btn-quiet"
              >
                Try again
              </button>
            )}
          </section>
        )}

        {step === "identifier" && chosen && (
          <section className="rise rise-3 max-w-2xl space-y-6">
            <div className="from-court pl-4">
              <Provenance from="court">Searching in</Provenance>
              <p className="mt-1 text-[0.9375rem]">
                {chosen.state} · {chosen.district} · <strong>{chosen.court}</strong>
              </p>
              <p className="mt-1 text-[0.75rem] leading-relaxed text-ink-soft">
                {chosen.known_court_id
                  ? `Already known here as “${chosen.known_court_name}”. The case will attach to it.`
                  : "New to the firm. A court will be created from these exact words."}
              </p>
            </div>

            <form onSubmit={askForCaptcha} className="space-y-5">
              <div className="flex flex-wrap items-baseline gap-x-5">
                {(["cnr", "case_number", "filing_number"] as SearchMode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    aria-pressed={mode === m}
                    className={`label border-b-2 pb-0.5 transition-colors ${
                      mode === m
                        ? "border-firm text-firm"
                        : "border-transparent hover:border-rule-strong hover:text-ink"
                    }`}
                  >
                    {MODE_LABEL[m]}
                  </button>
                ))}
              </div>

              {mode !== "cnr" && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Case type">
                    <select
                      className={inputClass}
                      value={caseType}
                      onChange={(e) => setCaseType(e.target.value)}
                      required
                    >
                      <option value="">— choose —</option>
                      {chosen.case_types.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Year">
                    <input
                      className={`${inputClass} ident`}
                      value={year}
                      onChange={(e) => setYear(e.target.value)}
                      placeholder="2024"
                      required
                    />
                  </Field>
                </div>
              )}

              <Field
                label={mode === "cnr" ? "CNR number" : MODE_LABEL[mode]}
                hint={
                  mode === "cnr"
                    ? "Sixteen characters. Every later refresh of this case will use it."
                    : undefined
                }
              >
                <input
                  className={`${inputClass} ident tracking-[0.08em]`}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={mode === "cnr" ? "KLER010012342024" : "412"}
                  required
                />
              </Field>

              <div className="flex gap-3">
                <button disabled={busy} className="btn btn-primary">
                  {busy ? "Filling in…" : "Next: CAPTCHA"}
                </button>
                <button type="button" onClick={() => setStep("court")} className="btn btn-quiet">
                  Back
                </button>
              </div>
            </form>
          </section>
        )}

        {step === "captcha" && captcha && (
          <section className="rise rise-3 max-w-xl space-y-5">
            {captcha.duplicate_case_id && (
              <Banner kind="caution">
                The firm already has a case with this CINO.{" "}
                <Link href={`/cases/${captcha.duplicate_case_id}`} className="underline">
                  Open it
                </Link>{" "}
                — searching again would only duplicate it.
              </Banner>
            )}

            {/* The one step in the whole system a machine is never allowed to
              take (ADR-0003), so it is given the room to look like a step. */}
            <form onSubmit={search} className="border border-rule-strong bg-leaf p-6">
              <Provenance from="court">The portal asks</Provenance>
              <p className="mt-2 max-w-md text-[0.8125rem] leading-relaxed text-ink-soft">
                Everything else is filled in. The portal replaces this image about every thirty
                seconds, so read it now.
              </p>

              <div className="mt-4 flex flex-wrap items-center gap-4">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={captcha.captcha}
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
                <label className="label mb-1.5 block text-firm">Type what you see</label>
                <input
                  className={`${inputClass} ident max-w-48 text-[1.1rem] uppercase tracking-[0.2em]`}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoFocus
                  required
                />
              </div>

              <div className="mt-5 flex gap-3">
                <button disabled={busy} className="btn btn-primary">
                  {busy ? "Searching…" : "Search DCMS"}
                </button>
                <button
                  type="button"
                  onClick={() => setStep("identifier")}
                  className="btn btn-quiet"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRestart(true)}
                  className="btn-plain ml-auto"
                >
                  Wrong court? Start over
                </button>
              </div>
            </form>
          </section>
        )}

        {step === "review" && result?.extracted && (
          <section className="rise rise-3 max-w-2xl space-y-10">
            <Banner kind="court">
              The portal found a case. Everything below is applied exactly as it reported it —
              review only asks what the portal cannot know.
            </Banner>

            <Sheet
              title="What the portal said"
              aside={<Provenance from="court">read-only</Provenance>}
            >
              <dl>
                <Reported label="CINO">
                  <span className="ident">{result.extracted.cino}</span>
                </Reported>
                <Reported label="Case type">{result.extracted.case_type ?? "—"}</Reported>
                <Reported label="Registration no.">
                  <span className="ident">{result.extracted.registration_number ?? "—"}</span>
                </Reported>
                <Reported label="Filing no.">
                  <span className="ident">{result.extracted.filing_number ?? "—"}</span>
                </Reported>
                <Reported label="Court Status">
                  <span className="text-court">{result.extracted.court_status ?? "—"}</span>
                </Reported>
                {result.extracted.subject && (
                  <Reported label="Subject">{result.extracted.subject}</Reported>
                )}
                {result.extracted.next_hearing && (
                  <Reported label="Next hearing">
                    <span className="ident">{formatDate(result.extracted.next_hearing)}</span>
                  </Reported>
                )}
                {result.extracted.last_hearing && (
                  <Reported label="Last hearing">
                    <span className="ident">{formatDate(result.extracted.last_hearing)}</span>
                  </Reported>
                )}
              </dl>
            </Sheet>

            <form onSubmit={submitReview} className="space-y-10">
              <Sheet
                title="Parties"
                hint="The portal knows petitioner and respondent, not sides — link each to a Party the firm already has, or add a new one."
                aside={<Provenance from="firm">the firm decides</Provenance>}
              >
                <div className="space-y-5">
                  {result.extracted.petitioner && (
                    <div className="space-y-1.5">
                      <span className="block text-[0.8125rem]">
                        Petitioner —{" "}
                        <span className="font-display italic text-ink-soft">
                          portal says &ldquo;{result.extracted.petitioner.name}
                          &rdquo;
                        </span>
                      </span>
                      <PartyPicker
                        value={petitionerParty}
                        onChange={setPetitionerParty}
                        initialTerm={result.extracted.petitioner.name}
                      />
                    </div>
                  )}

                  {result.extracted.petitioner_others.map((p, i) => (
                    <div key={i} className="ml-4 space-y-1.5 border-l border-rule pl-4">
                      <span className="block text-[0.8125rem]">
                        Also a petitioner —{" "}
                        <span className="font-display italic text-ink-soft">
                          portal says &ldquo;{p.name}&rdquo;
                        </span>
                      </span>
                      <p className="text-[0.75rem] leading-relaxed text-ink-soft">
                        Who &ldquo;{result.extracted!.petitioner?.name}&rdquo; stands in for on the
                        portal&rsquo;s own papers.
                      </p>
                      <PartyPicker
                        value={petitionerOtherParties[i] ?? null}
                        onChange={(choice) =>
                          setPetitionerOtherParties((prev) =>
                            prev.map((v, idx) => (idx === i ? choice : v)),
                          )
                        }
                        initialTerm={p.name}
                      />
                    </div>
                  ))}

                  {result.extracted.respondent && (
                    <div className="space-y-1.5">
                      <span className="block text-[0.8125rem]">
                        Respondent —{" "}
                        <span className="font-display italic text-ink-soft">
                          portal says &ldquo;{result.extracted.respondent.name}
                          &rdquo;
                        </span>
                      </span>
                      <PartyPicker
                        value={respondentParty}
                        onChange={setRespondentParty}
                        initialTerm={result.extracted.respondent.name}
                      />
                    </div>
                  )}

                  {result.extracted.respondent_others.map((p, i) => (
                    <div key={i} className="ml-4 space-y-1.5 border-l border-rule pl-4">
                      <span className="block text-[0.8125rem]">
                        Also a respondent —{" "}
                        <span className="font-display italic text-ink-soft">
                          portal says &ldquo;{p.name}&rdquo;
                        </span>
                      </span>
                      <p className="text-[0.75rem] leading-relaxed text-ink-soft">
                        Who &ldquo;{result.extracted!.respondent?.name}&rdquo; stands in for on the
                        portal&rsquo;s own papers.
                      </p>
                      <PartyPicker
                        value={respondentOtherParties[i] ?? null}
                        onChange={(choice) =>
                          setRespondentOtherParties((prev) =>
                            prev.map((v, idx) => (idx === i ? choice : v)),
                          )
                        }
                        initialTerm={p.name}
                      />
                    </div>
                  ))}

                  {result.extracted.petitioner && result.extracted.respondent && (
                    <Field label="Which one is the firm's client?">
                      <select
                        className={inputClass}
                        value={clientSide ?? "petitioner"}
                        onChange={(e) =>
                          setClientSide(e.target.value as "petitioner" | "respondent")
                        }
                      >
                        <option value="petitioner">
                          {result.extracted.petitioner.name} (petitioner)
                        </option>
                        <option value="respondent">
                          {result.extracted.respondent.name} (respondent)
                        </option>
                      </select>
                    </Field>
                  )}
                </div>
              </Sheet>

              <Sheet
                title="Advocates"
                hint="Anyone with a role here has this case in their own list, whether or not they lead it."
              >
                <div className="divide-y divide-rule">
                  {reviewAdvocates.map((a) => (
                    <div key={a.id} className="flex items-center gap-4 py-2">
                      <span className="flex-1 text-[0.8125rem]">{a.name}</span>
                      <select
                        className="field-input w-auto py-1 text-[0.75rem]"
                        value={roleFor(a)}
                        aria-label={`${a.name}'s role on this case`}
                        onChange={(e) =>
                          setReviewRoles((r) => ({
                            ...r,
                            [a.id]: e.target.value as AdvocateRole | "",
                          }))
                        }
                      >
                        <option value="">not on this case</option>
                        {(["lead", "assisting", "appearing"] as AdvocateRole[]).map((role) => (
                          <option key={role} value={role}>
                            {ADVOCATE_ROLE_LABEL[role]}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </Sheet>

              <Sheet
                title="Firm Status"
                hint="The firm's own view, independent of whatever the court says above."
              >
                <Field label="Is the firm actively working this case?">
                  <select
                    className={inputClass}
                    value={firmStatus}
                    onChange={(e) => setFirmStatus(e.target.value as FirmStatus)}
                  >
                    {(["active", "on_hold", "relinquished", "closed"] as FirmStatus[]).map((s) => (
                      <option key={s} value={s}>
                        {FIRM_STATUS_LABEL[s]}
                      </option>
                    ))}
                  </select>
                </Field>
              </Sheet>

              <div className="flex flex-wrap items-center gap-3">
                <button disabled={busy} className="btn btn-primary">
                  {busy ? "Creating…" : "Create case"}
                </button>
                <button type="button" onClick={() => setStep("done")} className="btn btn-quiet">
                  Skip — just keep the snapshot
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRestart(true)}
                  className="btn-plain ml-auto"
                >
                  Wrong court or case? Start over
                </button>
              </div>
            </form>
          </section>
        )}

        {step === "done" && result && (
          <section className="rise rise-3 max-w-3xl space-y-5">
            <Banner kind="note">
              The search came back and has been stored as snapshot{" "}
              <span className="ident">{result.snapshot_id.slice(0, 8)}</span> —{" "}
              {result.raw_length.toLocaleString()} characters. It is kept whatever happens next.
            </Banner>

            {!result.extracted && !result.parse_error && (
              <Banner kind="note">
                No case was found for that search. Check the identifier (and, for a Case
                No search, the case type and year) and try again.
              </Banner>
            )}

            {result.parse_error && (
              <Banner kind="error">Could not decode it: {result.parse_error}</Banner>
            )}

            <details className="border-t border-rule-strong pt-3" open={!!result.parse_error}>
              <summary className="label cursor-pointer text-ink">
                What came back (first 4,000 characters)
              </summary>
              <pre className="ident mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all bg-sunk p-3 text-[0.6875rem] leading-relaxed">
                {result.raw_preview}
              </pre>
            </details>

            {result.parsed && (
              <details className="border-t border-rule-strong pt-3">
                <summary className="label cursor-pointer text-ink">Decoded chunks</summary>
                <pre className="ident mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all bg-sunk p-3 text-[0.6875rem] leading-relaxed">
                  {JSON.stringify(result.parsed, null, 2).slice(0, 20000)}
                </pre>
              </details>
            )}

            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => {
                  setResult(null);
                  setCaptcha(null);
                  setCode("");
                  setStep("identifier");
                }}
                className="btn btn-quiet"
              >
                Search another
              </button>
              <Link href="/cases" className="btn btn-quiet">
                Back to cases
              </Link>
            </div>
          </section>
        )}
      </div>
    </Chrome>
  );
}
