"use client";

import { useEffect, useState } from "react";

import { Disclosure, Empty, Sheet, Waiting, inputClass } from "@/app/components/Chrome";
import { api, formatDate, isPast, type Advocate, type Task } from "@/lib/api";

type Deadline = "none" | "date" | "hearing";

/** What the deadline says on the row.
 *
 *  A task due before the next hearing shows the date it currently resolves to,
 *  and says so — the date is the court's, and will move when the court moves it. */
function Due({ t }: { t: Task }) {
  if (t.due_before_next_hearing) {
    return t.due_on ? (
      <span className={isPast(t.due_on) ? "text-caution" : undefined}>
        before <span className="ident">{formatDate(t.due_on)}</span>
        <span className="ml-1 text-ink-faint">(next hearing)</span>
      </span>
    ) : (
      <span className="text-ink-faint">before the next hearing — none scheduled</span>
    );
  }
  if (t.due_date) {
    return (
      <span className={isPast(t.due_date) ? "text-caution" : undefined}>
        by <span className="ident">{formatDate(t.due_date)}</span>
      </span>
    );
  }
  return <span className="text-ink-faint">no deadline</span>;
}

export function Tasks({ caseId }: { caseId: string }) {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [advocates, setAdvocates] = useState<Advocate[]>([]);
  const [showDone, setShowDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [deadline, setDeadline] = useState<Deadline>("none");
  const [dueDate, setDueDate] = useState("");
  const [busy, setBusy] = useState(false);

  // Bumped instead of calling a loader directly, so the fetch stays inside the
  // effect's callback - the same shape the rest of the case page uses.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .tasks(caseId, showDone)
      .then((data) => {
        if (!cancelled) setTasks(data);
      })
      .catch(() => {
        if (!cancelled) setTasks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, showDone, reloadKey]);

  useEffect(() => {
    api
      .advocates()
      .then((list) => {
        setAdvocates(list);
        setAssignee((current) => current || list[0]?.id || "");
      })
      .catch(() => setAdvocates([]));
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !assignee) return;
    setBusy(true);
    setError(null);
    try {
      await api.addTask(caseId, {
        title: title.trim(),
        assignee_id: assignee,
        due_date: deadline === "date" ? dueDate || null : null,
        due_before_next_hearing: deadline === "hearing",
      });
      setTitle("");
      setDeadline("none");
      setDueDate("");
      setAddOpen(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the task");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(t: Task) {
    await api.updateTask(caseId, t.id, { done: t.done_at === null });
    setReloadKey((k) => k + 1);
  }

  return (
    <Sheet
      className="rise rise-4"
      title="Tasks"
      hint="What someone owes on this case. Most litigation deadlines are before the next hearing — that kind moves when the court moves the date."
      aside={
        <button onClick={() => setShowDone((v) => !v)} className="btn-plain">
          {showDone ? "Hide done" : "Show done"}
        </button>
      }
    >
      <div className="mb-4">
        <Disclosure label="Add a task" open={addOpen} onOpenChange={setAddOpen}>
          <form onSubmit={add} className="space-y-2">
            <input
              autoFocus
              className={inputClass}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="File the counter statement"
              aria-label="What is owed"
            />
            <div className="flex flex-wrap gap-2">
              <select
                className={`${inputClass} flex-1`}
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                aria-label="Who owes it"
              >
                {advocates.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <select
                className={`${inputClass} flex-1`}
                value={deadline}
                onChange={(e) => setDeadline(e.target.value as Deadline)}
                aria-label="Deadline"
              >
                <option value="none">No deadline</option>
                <option value="hearing">Before the next hearing</option>
                <option value="date">By a date</option>
              </select>
            </div>
            {deadline === "date" && (
              <input
                type="date"
                className={`${inputClass} ident`}
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            )}
            <button disabled={busy || !title.trim()} className="btn btn-quiet">
              Add task
            </button>
            {error && <p className="text-[0.75rem] text-danger">{error}</p>}
          </form>
        </Disclosure>
      </div>

      {tasks === null ? (
        <Waiting />
      ) : tasks.length === 0 ? (
        <Empty>Nothing outstanding.</Empty>
      ) : (
        <ul>
          {tasks.map((t) => (
            <li
              key={t.id}
              className="row-mark group flex items-start gap-2.5 border-b border-rule py-2 text-[0.8125rem] last:border-0"
            >
              <input
                type="checkbox"
                className="mt-1 accent-[var(--firm)]"
                checked={t.done_at !== null}
                onChange={() => toggle(t)}
                aria-label={`Mark "${t.title}" done`}
              />
              <div className="min-w-0 flex-1">
                <div className={t.done_at ? "text-ink-faint line-through" : undefined}>
                  {t.title}
                </div>
                <div className="mt-0.5 text-[0.75rem] text-ink-soft">
                  {t.assignee.name} · <Due t={t} />
                  {t.done_by && ` · done by ${t.done_by.name}`}
                </div>
              </div>
              <button
                onClick={async () => {
                  await api.deleteTask(caseId, t.id);
                  setReloadKey((k) => k + 1);
                }}
                className="btn-plain opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
