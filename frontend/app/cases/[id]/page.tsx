"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Banner,
  Chrome,
  FirmStatusTag,
  PageHead,
  Provenance,
  Sheet,
  Waiting,
} from "@/app/components/Chrome";
import { FirmStatusPanel } from "./FirmStatusPanel";
import { Notes } from "./Notes";
import { PartyLine } from "./PartyLine";
import { Tasks } from "./Tasks";
import { Timeline } from "./Timeline";
import { Vakalath } from "./Vakalath";
import {
  ADVOCATE_ROLE_LABEL,
  api,
  caseLabel,
  clientsOf,
  formatDate,
  isPast,
  opponentsOf,
  type CaseDetail,
} from "@/lib/api";

/** One fact, with its name in the margin. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-b border-rule py-2 last:border-0">
      <dt className="label w-36 shrink-0 pt-0.5">{label}</dt>
      <dd className="min-w-0 flex-1 text-[0.8125rem]">{children}</dd>
    </div>
  );
}

function Missing({ children = "—" }: { children?: React.ReactNode }) {
  return <span className="text-ink-faint">{children}</span>;
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setCase] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Recording a hearing changes the case's derived next hearing date, so the
  // header has to be refetched when the timeline changes.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    // Guarded so that moving quickly between cases cannot let a slow earlier
    // response overwrite the one being looked at.
    let cancelled = false;
    api
      .case(id)
      .then((data) => {
        if (!cancelled) setCase(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load the case");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  if (error) {
    return (
      <Chrome>
        <Banner kind="error">{error}</Banner>
      </Chrome>
    );
  }
  if (!c) {
    return (
      <Chrome>
        <Waiting>Fetching the file</Waiting>
      </Chrome>
    );
  }

  const clients = c.parties.filter((p) => p.role === "client");
  const opponents = c.parties.filter((p) => p.role === "opposite_party");
  // Both halves of what the portal needs before it will search at all: a court
  // it can select (ADR-0004) and a CNR to search by.
  const canRefresh = c.court.is_complete && Boolean(c.cino);
  const named = clients.length > 0 || opponents.length > 0;

  return (
    <Chrome>
      <PageHead
        eyebrow={
          <Link href="/cases" className="label hover:text-firm">
            ← All cases
          </Link>
        }
        /* The case as a law report would head it: our client, then theirs. The
           number is a label, not the case's name (CONTEXT.md, "Filing Number"). */
        title={
          named ? (
            <>
              {clientsOf(c)}
              <span className="italic text-ink-faint"> v. </span>
              {opponentsOf(c)}
            </>
          ) : (
            <span className="ident text-[1.5rem]">{caseLabel(c)}</span>
          )
        }
        action={
          canRefresh ? (
            <Link href={`/cases/${id}/refresh`} className="btn btn-primary">
              Refresh from DCMS
            </Link>
          ) : (
            <button
              disabled
              title={
                c.court.is_complete
                  ? "A refresh searches by CNR, and this case has no CINO yet."
                  : "This court has not been identified on the DCMS portal yet."
              }
              className="btn btn-quiet"
            >
              Refresh from DCMS
            </button>
          )
        }
      >
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
          {named && <span className="ident text-[0.9375rem] font-medium">{caseLabel(c)}</span>}
          <span className="text-[0.8125rem] text-ink-soft">
            {c.court.name}
            {c.case_type ? ` · ${c.case_type}` : ""}
          </span>
          {/* Beside the case's own name, because the damage this prevents is
              an advocate acting on a case that is no longer the firm's. */}
          {c.firm_status === "relinquished" && <FirmStatusTag status={c.firm_status} loud />}
        </div>
      </PageHead>

      {!c.court.is_complete && (
        <div className="mb-6">
          <Banner kind="note">
            <strong>{c.court.name}</strong> has not been identified on the DCMS portal yet, so this
            case cannot be refreshed. That happens the first time a case in this court is ingested.
          </Banner>
        </div>
      )}

      {c.court.is_complete && !c.cino && (
        <div className="mb-6">
          <Banner kind="note">
            This case has no CINO yet, and a refresh searches by CNR. Find it on the portal by case
            or filing number, and the CINO comes back with it.
          </Banner>
        </div>
      )}

      <div className="grid gap-x-12 gap-y-10 lg:grid-cols-[1.65fr_1fr]">
        <div className="space-y-10">
          {/* The two sheets are split by provenance, not by subject. Everything
              in the second one is replaced wholesale by a refresh; nothing in
              the first one ever is (rule 1, ADR-0007). */}
          <Sheet
            className="rise rise-2"
            title="The firm's own"
            aside={<Provenance from="firm">never touched by a refresh</Provenance>}
          >
            <dl>
              <Row label="Client">
                {clients.length ? (
                  clients.map((p) => (
                    <PartyLine key={p.id} p={p} onChanged={() => setReloadKey((k) => k + 1)} />
                  ))
                ) : (
                  <Missing />
                )}
              </Row>
              <Row label="Opposite party">
                {opponents.length ? (
                  opponents.map((p) => (
                    <PartyLine key={p.id} p={p} onChanged={() => setReloadKey((k) => k + 1)} />
                  ))
                ) : (
                  <Missing />
                )}
              </Row>
              <Row label="Advocates">
                {c.assignments.length ? (
                  c.assignments.map((a) => (
                    <div key={a.id} className="flex items-baseline gap-2">
                      {a.advocate.name}
                      <span className="label text-[0.5625rem]">{ADVOCATE_ROLE_LABEL[a.role]}</span>
                    </div>
                  ))
                ) : (
                  <Missing />
                )}
              </Row>
              <Row label="Vakalath">
                <Vakalath c={c} onChanged={setCase} />
              </Row>
              <Row label="Tags">
                {c.tags.length ? (
                  <span className="flex flex-wrap gap-x-2 gap-y-1">
                    {c.tags.map((t) => (
                      <span
                        key={t.id}
                        className="border border-rule bg-leaf px-1.5 py-0.5 text-[0.75rem]"
                      >
                        {t.name}
                      </span>
                    ))}
                  </span>
                ) : (
                  <Missing />
                )}
              </Row>
            </dl>
          </Sheet>

          <Sheet
            className="rise rise-3"
            title="From the court"
            aside={<Provenance from="court">replaced whole by a refresh</Provenance>}
          >
            <dl>
              <Row label="Registration no.">
                {c.registration_number ? (
                  <span className="ident">{c.registration_number}</span>
                ) : (
                  <Missing />
                )}
              </Row>
              <Row label="Filing no.">
                {c.filing_number ? <span className="ident">{c.filing_number}</span> : <Missing />}
              </Row>
              <Row label="CINO">
                {c.cino ? (
                  <span className="ident">{c.cino}</span>
                ) : (
                  <Missing>not known yet</Missing>
                )}
              </Row>
              {c.act_sections.length > 0 && (
                <Row label="Acts & Section">
                  {c.act_sections.map((a) => (
                    <div key={a.id}>
                      {a.act_name}
                      {a.section && <span className="ident text-ink-soft">/{a.section}</span>}
                    </div>
                  ))}
                </Row>
              )}
              {c.crime_details && (
                <Row label="Crime Details">
                  <div className="space-y-0.5">
                    {c.crime_details.fir_no && (
                      <div>
                        FIR{" "}
                        <span className="ident">
                          {c.crime_details.fir_no}
                          {c.crime_details.fir_year ? `/${c.crime_details.fir_year}` : ""}
                        </span>
                      </div>
                    )}
                    {c.crime_details.cr_no && (
                      <div>
                        CR No. <span className="ident">{c.crime_details.cr_no}</span>
                      </div>
                    )}
                    {c.crime_details.police_station && <div>{c.crime_details.police_station}</div>}
                    {c.crime_details.investigating_officer && (
                      <div className="text-[0.75rem] text-ink-soft">
                        Investigating officer: {c.crime_details.investigating_officer}
                        {c.crime_details.rank ? ` (${c.crime_details.rank})` : ""}
                      </div>
                    )}
                    {!c.crime_details.fir_no &&
                      !c.crime_details.cr_no &&
                      !c.crime_details.police_station &&
                      !c.crime_details.investigating_officer && (
                        <Missing>On record with the court, no further detail available</Missing>
                      )}
                  </div>
                </Row>
              )}
            </dl>
          </Sheet>

          <Timeline caseId={id} onCaseChanged={() => setReloadKey((k) => k + 1)} />
        </div>

        <div className="space-y-10">
          {/* Read off the hearings and never stored, so it is set as a reading
              of them rather than as a field of the case. */}
          <Sheet
            className="rise rise-2"
            title="Next hearing"
            hint="Read from the hearings below, never stored separately."
          >
            {c.next_hearing_date ? (
              <>
                <p
                  className={`ident text-[1.5rem] leading-none ${
                    isPast(c.next_hearing_date) ? "text-caution" : ""
                  }`}
                >
                  {formatDate(c.next_hearing_date)}
                </p>
                {isPast(c.next_hearing_date) && (
                  <p className="mt-2 text-[0.75rem] text-caution">
                    That date has passed with nothing recorded against it.
                  </p>
                )}
              </>
            ) : (
              <p className="text-[0.8125rem] italic text-ink-soft">No date on record.</p>
            )}
          </Sheet>

          {/* Two statuses, deliberately shown apart. They legitimately disagree:
              a disposed case under appeal is the firm's most active work. */}
          <FirmStatusPanel c={c} onChanged={setCase} />

          <Tasks caseId={id} />

          <Notes caseId={id} />
        </div>
      </div>
    </Chrome>
  );
}
