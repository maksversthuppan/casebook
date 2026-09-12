"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ThemeToggle } from "@/app/components/Theme";
import { ApiError, FIRM_STATUS_LABEL, api, type Advocate, type FirmStatus } from "@/lib/api";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/cases", label: "Cases" },
  { href: "/ingest", label: "Find on DCMS" },
  { href: "/cases/new", label: "Add by hand" },
];

/** Signs the advocate out of view until we know who they are, then renders the
 *  app shell. Everyone in the firm sees everything; the name in the corner is
 *  there because authorship is what the system relies on instead of permissions.
 *
 *  The masthead is a law report's: wordmark, a double rule, and the day's date
 *  set in the register hand — a cause list is always dated. */
export function Chrome({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Advocate | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
      })
      .finally(() => setChecked(true));
  }, [router]);

  if (!checked) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="label animate-pulse">Opening the register</p>
      </div>
    );
  }
  if (!me) return null;

  const activeHref = NAV.filter((n) =>
    n.href === "/" ? pathname === "/" : pathname === n.href || pathname.startsWith(`${n.href}/`),
  ).sort((a, b) => b.href.length - a.href.length)[0]?.href;

  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <div className="flex min-h-full flex-col">
      <header className="double-rule sticky top-0 z-50 bg-paper">
        <div className="mx-auto flex w-full max-w-[76rem] flex-wrap items-baseline gap-x-6 gap-y-2 px-6 pb-2.5 pt-3 sm:px-8">
          <Link href="/" className="font-display text-[1.35rem] font-light leading-none">
            Case <span className="italic">Repository</span>
          </Link>

          <nav className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            {NAV.map((item) => {
              // Longest match wins, or /cases/new would light up "Cases" too.
              const active = item.href === activeHref;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`label border-b-2 pb-0.5 transition-colors ${
                    active
                      ? "border-firm text-firm"
                      : "border-transparent hover:border-rule-strong hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <span className="ident hidden text-[0.7rem] text-ink-faint lg:inline">{today}</span>
            <ThemeToggle />
            <span className="text-[0.8125rem]">{me.name}</span>
            <button
              onClick={async () => {
                await api.logout();
                router.replace("/login");
              }}
              className="btn-plain"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[76rem] flex-1 px-6 py-9 sm:px-8">{children}</main>

      <footer className="mx-auto w-full max-w-[76rem] px-6 pb-8 sm:px-8">
        <p className="border-t border-rule pt-3 text-[0.6875rem] italic text-ink-faint">
          The firm&rsquo;s own record. DCMS is consulted one case at a time, by hand.
        </p>
      </footer>
    </div>
  );
}

/** The page's own masthead: a title in the reading face, an optional line of
 *  explanation, and whatever the page's one action is, kept to the right. */
export function PageHead({
  title,
  lede,
  eyebrow,
  action,
  children,
}: {
  title: React.ReactNode;
  lede?: React.ReactNode;
  eyebrow?: React.ReactNode;
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="rise rise-1 mb-8">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          {eyebrow && <div className="mb-1.5">{eyebrow}</div>}
          <h1 className="font-display text-[1.9rem] font-light leading-tight tracking-[-0.01em]">
            {title}
          </h1>
          {children}
        </div>
        {/* ml-auto keeps the action to the right even when a long case name
            pushes it onto its own line. */}
        {action && <div className="ml-auto flex shrink-0 flex-wrap gap-2">{action}</div>}
      </div>
      {lede && <p className="mt-3 max-w-2xl text-[0.8125rem] text-ink-soft">{lede}</p>}
      <div className="mt-4 border-t border-rule-strong" />
    </div>
  );
}

/** Re-fetches the page's own data from the server. Distinct from "Refresh from
 *  DCMS": that is a deliberate, CAPTCHA-gated act against the court's portal
 *  (CONTEXT.md, "Refresh"), while this is only "read what's already here
 *  again", for when a page glitched or another advocate changed something. */
export function ReloadButton({
  onReload,
  busy = false,
}: {
  onReload: () => void;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onReload}
      disabled={busy}
      title="Reload this page's own data — not a Refresh from DCMS"
      className="btn btn-quiet"
    >
      {busy ? "Reloading…" : "Reload"}
    </button>
  );
}

/** A section of a page. Announced by a small-caps label over a rule, the way a
 *  law report announces one — not drawn as a box floating on grey. */
export function Sheet({
  title,
  hint,
  aside,
  className = "",
  children,
}: {
  title: React.ReactNode;
  hint?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={className}>
      <div className="flex items-baseline justify-between gap-3 border-b border-rule-strong pb-1.5">
        <h2 className="label text-ink">{title}</h2>
        {aside}
      </div>
      {hint && <p className="mt-2 max-w-prose text-xs leading-relaxed text-ink-soft">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs leading-relaxed text-ink-soft">{hint}</span>}
    </label>
  );
}

/** A form that stays out of the way until it's wanted: one line naming the
 *  action and what it's for, expanding in place rather than in a modal - so
 *  whatever it's being added to (a timeline, a list) stays visible while
 *  filling it in. */
export function Disclosure({
  label,
  hint,
  open,
  onOpenChange,
  className = "",
  children,
}: {
  label: string;
  hint?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  className?: string;
  children: React.ReactNode;
}) {
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => onOpenChange(true)}
        className={`group block w-full text-left ${className}`}
      >
        <span className="label text-ink-soft transition-colors group-hover:text-firm">
          + {label}
        </span>
        {hint && (
          <span className="mt-1 block text-[0.75rem] leading-relaxed text-ink-faint">{hint}</span>
        )}
      </button>
    );
  }
  return (
    <div className={className}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="label text-ink">{label}</h3>
          {hint && <p className="mt-1 text-[0.75rem] leading-relaxed text-ink-soft">{hint}</p>}
        </div>
        <button type="button" onClick={() => onOpenChange(false)} className="btn-plain shrink-0">
          cancel
        </button>
      </div>
      <div className="mt-2.5 space-y-2.5">{children}</div>
    </div>
  );
}

export const inputClass = "field-input";

/** Which voice a fact speaks in. The court gets a filled square in teal, the
 *  firm's own hand a pilcrow in blue — the distinction the whole system turns
 *  on, made visible wherever the two sit side by side (DESIGN.md, ADR-0007).
 *  The glyph carries it on its own, so the colour is reinforcement rather than
 *  the only signal. */
export function Provenance({
  from,
  children,
}: {
  from: "court" | "firm";
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-baseline gap-1.5 text-[0.6875rem] ${
        from === "court" ? "text-court" : "text-firm"
      }`}
    >
      <span aria-hidden className="text-[0.6em] leading-none">
        {from === "court" ? "▪" : "¶"}
      </span>
      {children}
    </span>
  );
}

/** The firm's own status, wherever a Case is shown.
 *
 *  Relinquished is the only one that shouts, and deliberately: the damage this
 *  prevents is an advocate acting on a Case that is no longer the firm's. On
 *  hold looks quiet because the firm still holds that one and is still
 *  answerable for it - the two are never collapsed (CONTEXT.md, "Firm Status"). */
export function FirmStatusTag({ status, loud = false }: { status: FirmStatus; loud?: boolean }) {
  if (status === "relinquished") {
    return (
      <span title="The firm has given this case up" className={`stamp ${loud ? "stamp-loud" : ""}`}>
        Relinquished
      </span>
    );
  }
  return <span>{FIRM_STATUS_LABEL[status]}</span>;
}

const BANNER_TONE = {
  error: "border-danger bg-danger-wash text-ink",
  note: "border-rule-strong bg-leaf text-ink-soft",
  court: "border-court bg-court-wash text-ink",
  caution: "border-caution bg-caution-wash text-ink",
} as const;

export function Banner({
  kind,
  children,
}: {
  kind: keyof typeof BANNER_TONE;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`border-l-[3px] px-3.5 py-2.5 text-[0.8125rem] leading-relaxed ${BANNER_TONE[kind]}`}
    >
      {children}
    </div>
  );
}

/** Where a page is waiting on the network. Said in the register's own voice
 *  rather than as a spinner. */
export function Waiting({ children = "Loading" }: { children?: React.ReactNode }) {
  return <p className="label animate-pulse py-6">{children}</p>;
}

/** Nothing here — stated plainly, in the margin voice, not as an illustration. */
export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-1 text-[0.8125rem] italic text-ink-soft">{children}</p>;
}
