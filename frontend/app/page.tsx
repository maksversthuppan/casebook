"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Banner, Chrome, Empty, PageHead, Sheet, Waiting } from "@/app/components/Chrome";
import {
  api,
  caseLabel,
  clientsOf,
  formatDate,
  type CaseSummary,
  type Dashboard,
  type Hearing,
  type Task,
} from "@/lib/api";

/** A hearing on the day's list: the date in the margin, then a rule in the
 *  colour of whoever said so, then the case. Court-reported and firm-recorded
 *  dates sit in one list and are told apart without reading a word. */
function HearingRow({ h, c, tone }: { h: Hearing; c: CaseSummary; tone?: "caution" }) {
  return (
    <li className="row-mark flex items-baseline gap-3 border-b border-rule py-2.5 last:border-0">
      <time
        dateTime={h.date}
        className={`ident w-[5.5rem] shrink-0 text-[0.75rem] ${
          tone === "caution" ? "text-caution" : "text-ink"
        }`}
      >
        {formatDate(h.date)}
      </time>

      <div
        className={`min-w-0 flex-1 border-l-2 pl-3 ${
          h.source === "court" ? "border-court" : "border-firm"
        }`}
        title={h.source === "court" ? "Reported by DCMS" : "Noted by the firm"}
      >
        <Link
          href={`/cases/${c.id}`}
          className="ident text-[0.8125rem] font-medium hover:text-firm hover:underline"
        >
          {caseLabel(c)}
        </Link>
        <div className="truncate text-[0.8125rem] text-ink-soft">
          {clientsOf(c)}
          {h.purpose && <span className="font-display italic"> — {h.purpose}</span>}
        </div>
      </div>
    </li>
  );
}

/** A task's deadline, said the way the firm says it. One due before the next
 *  hearing shows the date it currently resolves to and names the reason, since
 *  that date belongs to the court and will move when the court moves it. */
function TaskDue({ t }: { t: Task }) {
  if (t.due_before_next_hearing) {
    return t.due_on ? (
      <>
        before <span className="ident">{formatDate(t.due_on)}</span> (next hearing)
      </>
    ) : (
      <>before the next hearing — none scheduled</>
    );
  }
  if (t.due_date) {
    return (
      <>
        by <span className="ident">{formatDate(t.due_date)}</span>
      </>
    );
  }
  return <>no deadline</>;
}

export default function Home() {
  const [board, setBoard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setBoard)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not load the dashboard"),
      );
  }, []);

  if (error) {
    return (
      <Chrome>
        <Banner kind="error">{error}</Banner>
      </Chrome>
    );
  }
  if (!board) {
    return (
      <Chrome>
        <Waiting>Reading the day</Waiting>
      </Chrome>
    );
  }

  return (
    <Chrome>
      <PageHead
        eyebrow={<span className="label">The day&rsquo;s list</span>}
        title="Today"
        lede="Cases you hold a role on. Anything the firm has closed or given up is left out."
      />

      <div className="grid gap-x-12 gap-y-10 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-10">
          <Sheet
            className="rise rise-2"
            title="Hearings to prepare for"
            aside={
              <span className="ident text-[0.6875rem] text-ink-faint">
                to {formatDate(board.horizon)}
              </span>
            }
          >
            {board.hearings.length === 0 ? (
              <Empty>Nothing listed in the week ahead.</Empty>
            ) : (
              <ul>
                {board.hearings.map(({ hearing, case: c }) => (
                  <HearingRow key={hearing.id} h={hearing} c={c} />
                ))}
              </ul>
            )}
          </Sheet>

          {/* Not work coming, but a record with a hole in it: the court was going
              to sit and nobody wrote down what happened. */}
          {board.hearings_passed.length > 0 && (
            <Sheet
              className="rise rise-3"
              title={<span className="text-caution">Passed with nothing recorded</span>}
              hint="The date went by and no outcome was written against it. Nothing is wrong — something is missing."
            >
              <ul>
                {board.hearings_passed.map(({ hearing, case: c }) => (
                  <HearingRow key={hearing.id} h={hearing} c={c} tone="caution" />
                ))}
              </ul>
            </Sheet>
          )}
        </div>

        <div className="space-y-10">
          <Sheet
            className="rise rise-3"
            title="Tasks you owe"
            hint="Soonest first; work with no deadline last."
          >
            {board.tasks.length === 0 ? (
              <Empty>Nothing outstanding.</Empty>
            ) : (
              <ul>
                {board.tasks.map((t) => (
                  <li key={t.id} className="row-mark border-b border-rule py-2.5 last:border-0">
                    <div className="text-[0.8125rem]">{t.title}</div>
                    <div className="mt-0.5 text-[0.75rem] text-ink-soft">
                      <TaskDue t={t} />
                      {" · "}
                      <Link
                        href={`/cases/${t.case_id}`}
                        className="hover:text-firm hover:underline"
                      >
                        open the case
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Sheet>

          <Sheet
            className="rise rise-4"
            title="Not confirmed with DCMS lately"
            hint={`Nothing is wrong with these — they are unconfirmed, not out of date. Over ${board.stale_after_days} days.`}
          >
            {board.stale_cases.length === 0 ? (
              <Empty>Everything has been confirmed recently.</Empty>
            ) : (
              <ul>
                {board.stale_cases.map((c) => (
                  <li
                    key={c.id}
                    className="row-mark flex flex-wrap items-baseline justify-between gap-x-3 border-b border-rule py-2.5 last:border-0"
                  >
                    <Link
                      href={`/cases/${c.id}`}
                      className="ident text-[0.8125rem] font-medium hover:text-firm hover:underline"
                    >
                      {caseLabel(c)}
                    </Link>
                    <span className="text-[0.75rem] text-ink-soft">
                      {c.last_refreshed_at ? (
                        <>
                          confirmed{" "}
                          <span className="ident">
                            {new Date(c.last_refreshed_at).toLocaleDateString("en-GB")}
                          </span>
                        </>
                      ) : (
                        "never confirmed"
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Sheet>
        </div>
      </div>
    </Chrome>
  );
}
