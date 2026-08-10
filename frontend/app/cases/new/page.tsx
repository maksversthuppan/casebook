"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Banner, Chrome, Field, PageHead, Sheet, inputClass } from "@/app/components/Chrome";
import { PartyPicker, type PartyChoice } from "./PartyPicker";
import { ADVOCATE_ROLE_LABEL, api, type Advocate, type AdvocateRole, type Court } from "@/lib/api";

interface Row {
  choice: PartyChoice | null;
}

export default function NewCasePage() {
  const router = useRouter();

  const [courts, setCourts] = useState<Court[]>([]);
  const [advocates, setAdvocates] = useState<Advocate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [courtId, setCourtId] = useState("");
  const [newCourtName, setNewCourtName] = useState("");
  const [clients, setClients] = useState<Row[]>([{ choice: null }]);
  const [opponents, setOpponents] = useState<Row[]>([{ choice: null }]);
  const [roles, setRoles] = useState<Record<string, AdvocateRole | "">>({});
  const [caseType, setCaseType] = useState("");
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [filingNumber, setFilingNumber] = useState("");
  const [cino, setCino] = useState("");
  const [tags, setTags] = useState("");

  useEffect(() => {
    api
      .courts()
      .then(setCourts)
      .catch(() => setCourts([]));
    api
      .advocates()
      .then(setAdvocates)
      .catch(() => setAdvocates([]));
  }, []);

  function partiesPayload() {
    const out: unknown[] = [];
    clients.forEach((r, i) => {
      if (!r.choice) return;
      out.push({ ...pick(r.choice), role: "client", position: i + 1 });
    });
    opponents.forEach((r, i) => {
      if (!r.choice) return;
      out.push({ ...pick(r.choice), role: "opposite_party", position: i + 1 });
    });
    return out;
  }

  function pick(c: PartyChoice) {
    return c.party_id ? { party_id: c.party_id } : { new_party: c.new_party };
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const assignments = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([advocate_id, role]) => ({ advocate_id, role }));

    if (assignments.length === 0) {
      setError("Give at least one advocate a role on this case.");
      return;
    }
    if (!clients.some((r) => r.choice)) {
      setError("A case needs at least one client.");
      return;
    }

    setBusy(true);
    try {
      const created = await api.createCase({
        ...(courtId ? { court_id: courtId } : { new_court_name: newCourtName.trim() }),
        parties: partiesPayload(),
        assignments,
        case_type: caseType || null,
        registration_number: registrationNumber || null,
        filing_number: filingNumber || null,
        cino: cino.trim() || null,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
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
          eyebrow={<span className="label">Out of the ordinary way in</span>}
          title="Add a case by hand"
          lede="For a case the portal cannot answer for yet — a plaint filed this morning has no registration number and no CINO for days, and still needs somewhere to live. Finding it on DCMS is the usual way in."
        />

        <form onSubmit={submit} className="space-y-10">
          {error && <Banner kind="error">{error}</Banner>}

          <Sheet className="rise rise-2" title="Court">
            <div className="space-y-4">
              <Field label="Choose one the firm already uses">
                <select
                  className={inputClass}
                  value={courtId}
                  onChange={(e) => {
                    setCourtId(e.target.value);
                    if (e.target.value) setNewCourtName("");
                  }}
                >
                  <option value="">— add a new one below —</option>
                  {courts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.is_complete ? "" : "  (not identified on DCMS yet)"}
                    </option>
                  ))}
                </select>
              </Field>
              {!courtId && (
                <Field
                  label="Or add a new court"
                  hint="It starts provisional — a name only. It gains its DCMS district and establishment the first time a case there is ingested."
                >
                  <input
                    className={inputClass}
                    value={newCourtName}
                    onChange={(e) => setNewCourtName(e.target.value)}
                    placeholder="Munsiff Court, Ernakulam"
                    required={!courtId}
                  />
                </Field>
              )}
            </div>
          </Sheet>

          <Sheet
            className="rise rise-3"
            title="Parties"
            hint="A Party is recorded once and reused in every case it appears in, so the second case against the same opponent links to the same record."
          >
            <div className="space-y-6">
              <div className="space-y-2">
                <span className="label text-ink">Client(s)</span>
                {clients.map((row, i) => (
                  <PartyPicker
                    key={i}
                    value={row.choice}
                    onChange={(choice) =>
                      setClients((rows) => rows.map((r, j) => (i === j ? { choice } : r)))
                    }
                  />
                ))}
                <button
                  type="button"
                  className="btn-plain"
                  onClick={() => setClients((r) => [...r, { choice: null }])}
                >
                  + another client
                </button>
              </div>

              <div className="space-y-2">
                <span className="label text-ink">Opposite party</span>
                {opponents.map((row, i) => (
                  <PartyPicker
                    key={i}
                    value={row.choice}
                    onChange={(choice) =>
                      setOpponents((rows) => rows.map((r, j) => (i === j ? { choice } : r)))
                    }
                  />
                ))}
                <button
                  type="button"
                  className="btn-plain"
                  onClick={() => setOpponents((r) => [...r, { choice: null }])}
                >
                  + another opposite party
                </button>
              </div>
            </div>
          </Sheet>

          <Sheet
            className="rise rise-4"
            title="Advocates"
            hint="Anyone with a role here has this case in their own list, whether or not they lead it."
          >
            <div className="divide-y divide-rule">
              {advocates.map((a) => (
                <div key={a.id} className="flex items-center gap-4 py-2">
                  <span className="flex-1 text-[0.8125rem]">{a.name}</span>
                  <select
                    className="field-input w-auto py-1 text-[0.75rem]"
                    value={roles[a.id] ?? ""}
                    aria-label={`${a.name}'s role on this case`}
                    onChange={(e) =>
                      setRoles((r) => ({
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
            className="rise rise-5"
            title="Numbers"
            hint="All optional. A case works with none of them — none of these is its identity."
          >
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Case type">
                  <input
                    className={inputClass}
                    value={caseType}
                    onChange={(e) => setCaseType(e.target.value)}
                    placeholder="OS"
                  />
                </Field>
                <Field label="Registration number">
                  <input
                    className={`${inputClass} ident`}
                    value={registrationNumber}
                    onChange={(e) => setRegistrationNumber(e.target.value)}
                    placeholder="OS/412/2024"
                  />
                </Field>
                <Field label="Filing number">
                  <input
                    className={`${inputClass} ident`}
                    value={filingNumber}
                    onChange={(e) => setFilingNumber(e.target.value)}
                    placeholder="1187/2024"
                  />
                </Field>
                <Field label="CINO" hint="Needed before this case can be refreshed from DCMS.">
                  <input
                    className={`${inputClass} ident`}
                    value={cino}
                    onChange={(e) => setCino(e.target.value)}
                    placeholder="KLER010012342024"
                  />
                </Field>
              </div>
              <Field label="Tags" hint="Comma separated.">
                <input
                  className={inputClass}
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="land, urgent"
                />
              </Field>
            </div>
          </Sheet>

          <div className="flex gap-3">
            <button type="submit" disabled={busy} className="btn btn-primary">
              {busy ? "Creating…" : "Create case"}
            </button>
            <button type="button" onClick={() => router.back()} className="btn btn-quiet">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </Chrome>
  );
}
