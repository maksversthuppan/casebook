"use client";

import { useEffect, useState } from "react";

import { Disclosure, Empty, Provenance, Sheet, Waiting, inputClass } from "@/app/components/Chrome";
import { api, type Advocate, type InternalNote } from "@/lib/api";

/** Notes are about the case as a whole, so they stay off the Timeline - they
 *  are not about a day. */
export function Notes({ caseId }: { caseId: string }) {
  const [notes, setNotes] = useState<InternalNote[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [me, setMe] = useState<Advocate | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .notes(caseId)
      .then((data) => {
        if (!cancelled) setNotes(data);
      })
      .catch(() => {
        if (!cancelled) setNotes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, reloadKey]);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      await api.addNote(caseId, body.trim());
      setBody("");
      setAddOpen(false);
      setReloadKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      className="rise rise-5"
      title="Notes"
      hint="About the case as a whole — instructions, strategy, a warning for whoever picks the file up. Not about a day, so not on the Timeline."
    >
      <div className="mb-4">
        <Disclosure label="Add a note" open={addOpen} onOpenChange={setAddOpen}>
          <form onSubmit={add} className="space-y-2">
            <textarea
              className={`${inputClass} hand min-h-20 text-[0.9375rem]`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Client is hard to reach on the mobile — call the landline after 6."
              aria-label="A note about this case"
              autoFocus
            />
            <button disabled={busy} className="btn btn-quiet">
              Add note
            </button>
          </form>
        </Disclosure>
      </div>

      {notes === null ? (
        <Waiting />
      ) : notes.length === 0 ? (
        <Empty>No notes.</Empty>
      ) : (
        <ul className="space-y-4">
          {notes.map((n) => (
            <li key={n.id} className="group from-firm pl-3.5">
              <p className="hand whitespace-pre-wrap">{n.body}</p>
              <p className="mt-1 flex items-center gap-3">
                <Provenance from="firm">{n.author.name}</Provenance>
                {n.author.id === me?.id && (
                  <button
                    onClick={async () => {
                      await api.deleteNote(caseId, n.id);
                      setReloadKey((k) => k + 1);
                    }}
                    className="btn-plain ml-auto opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    remove
                  </button>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
