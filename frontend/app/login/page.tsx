"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Banner, Field, inputClass } from "@/app/components/Chrome";
import { ThemeToggle } from "@/app/components/Theme";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email, password);
      router.replace("/cases");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative grid flex-1 lg:grid-cols-[1.25fr_1fr]">
      {/* The sign-in screen is outside the app shell, so it carries its own
          copy — otherwise somebody landing here in the wrong theme has no way
          to change it until they are already in. */}
      <div className="absolute right-6 top-6 z-10">
        <ThemeToggle />
      </div>

      {/* The plate. Ruled paper behind an oversized masthead — the only place in
          the app with room to say what this thing is. The rules are held well
          under the type; they are a texture, not a grid to read. */}
      <section
        className="relative hidden flex-col justify-between overflow-hidden border-r border-rule-strong px-14 py-14 lg:flex"
        style={{
          backgroundImage:
            "repeating-linear-gradient(to bottom, transparent 0 33px, color-mix(in srgb, var(--rule) 50%, transparent) 33px 34px)",
          backgroundColor: "var(--leaf)",
        }}
      >
        <p className="label rise rise-1">Kerala · District Courts</p>

        <div className="rise rise-2 relative">
          <h1 className="font-display text-[4.5rem] font-light leading-[0.95] tracking-[-0.02em]">
            Case
            <br />
            <span className="italic">Repository</span>
          </h1>
          <div className="double-rule mt-6 w-40" />
          <p className="hand mt-6 max-w-md text-ink-soft">
            The firm&rsquo;s own record of every proceeding it acts in. The portal is an outside
            reference, consulted one case at a time.
          </p>
        </div>

        <p className="rise rise-3 max-w-md text-[0.75rem] leading-relaxed text-ink-faint">
          Nothing here is fetched on a schedule, and no CAPTCHA is ever read by anything but a
          person.
        </p>
      </section>

      <section className="flex flex-1 items-center justify-center px-6 py-16">
        <form onSubmit={submit} className="rise rise-2 w-full max-w-sm">
          <div className="lg:hidden">
            <h1 className="font-display text-[2.5rem] font-light leading-none">
              Case <span className="italic">Repository</span>
            </h1>
            <div className="double-rule mt-4 w-28" />
          </div>

          <p className="label mt-8 lg:mt-0">Sign in</p>
          <div className="mt-1.5 mb-7 border-t border-rule-strong" />

          {error && (
            <div className="mb-5">
              <Banner kind="error">{error}</Banner>
            </div>
          )}

          <div className="space-y-5">
            <Field label="Email">
              <input
                className={inputClass}
                type="email"
                value={email}
                autoComplete="username"
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Field>
            <Field label="Password">
              <input
                className={inputClass}
                type="password"
                value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="btn btn-primary mt-7 w-full justify-center"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}
