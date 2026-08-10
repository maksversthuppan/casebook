"use client";

import { useLayoutEffect, useSyncExternalStore } from "react";

/** What the advocate chose. "system" defers to the OS and keeps following it. */
export type ThemePref = "light" | "system" | "dark";

const KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

/** Runs synchronously in <head>, before the browser paints anything.
 *
 *  It resolves "system" itself rather than leaving it to CSS, so `data-theme`
 *  on <html> is always a concrete light or dark — which is what lets globals.css
 *  hold each palette exactly once instead of repeating the dark one for a
 *  prefers-color-scheme block as well.
 *
 *  No stylesheet fallback for the no-JS case on purpose: every screen in this
 *  app is a client component that fetches its own data, so without JavaScript
 *  there is nothing to theme. */
export const THEME_INIT = `(function(){try{var p=localStorage.getItem(${JSON.stringify(
  KEY,
)});var d=p==="dark"||(p!=="light"&&matchMedia(${JSON.stringify(
  DARK_QUERY,
)}).matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){}})()`;

function readStored(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function resolve(pref: ThemePref): "light" | "dark" {
  if (pref !== "system") return pref;
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function apply(pref: ThemePref) {
  document.documentElement.dataset.theme = resolve(pref);
}

/* localStorage is state that lives outside React, so it is read through
 * useSyncExternalStore rather than mirrored into useState from an effect. That
 * keeps the server render ("system") and the hydration render in agreement —
 * React re-reads the real value immediately afterwards — and means there is no
 * setState-in-an-effect to go wrong. */
const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // Another tab, or another copy of this control on the same page.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

const getServerSnapshot = (): ThemePref => "system";

const ICON = {
  light: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </>
  ),
  system: (
    <>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </>
  ),
  dark: <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />,
} as const;

const LABEL: Record<ThemePref, string> = {
  light: "Light",
  system: "Match the system",
  dark: "Dark",
};

const ORDER: ThemePref[] = ["light", "system", "dark"];

/** Light / system / dark, as three ruled buttons rather than one switch: a
 *  two-state toggle cannot express "follow the OS", which is the default and
 *  the setting most people will leave it on. */
export function ThemeToggle() {
  const pref = useSyncExternalStore(subscribe, readStored, getServerSnapshot);

  // Before paint rather than after, so the choice is never briefly wrong. This
  // also re-applies the attribute in development, where Strict Mode's remount
  // resets <html> to the attributes React manages from JSX and drops the one
  // the head script set. A no-op in production.
  useLayoutEffect(() => {
    apply(pref);
  }, [pref]);

  // "System" means it keeps tracking the OS, not that it read it once.
  useLayoutEffect(() => {
    if (pref !== "system") return;
    const mq = window.matchMedia(DARK_QUERY);
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  function choose(next: ThemePref) {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // A locked-down browser can refuse storage. Apply it anyway so the button
      // does something for this session rather than nothing at all.
      apply(next);
      return;
    }
    listeners.forEach((l) => l());
  }

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="flex items-center rounded-[2px] border border-rule-strong"
    >
      {ORDER.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => choose(p)}
          aria-pressed={pref === p}
          aria-label={LABEL[p]}
          title={LABEL[p]}
          className={`p-1.5 transition-colors first:rounded-l-[1px] last:rounded-r-[1px] ${
            pref === p
              ? "bg-firm text-on-accent"
              : "text-ink-faint hover:bg-firm-wash hover:text-firm"
          }`}
        >
          <svg
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {ICON[p]}
          </svg>
        </button>
      ))}
    </div>
  );
}
