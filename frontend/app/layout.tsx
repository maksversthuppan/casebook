import type { Metadata } from "next";
import localFont from "next/font/local";

import { THEME_INIT } from "./components/Theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "Case Repository",
  description: "The firm's record of its cases.",
};

/* Three faces, three jobs — see DESIGN.md.
 *
 * The files are vendored into app/fonts/ rather than fetched from Google, so
 * the office server still builds and runs without reaching the internet. That
 * was the reason there were no web fonts here at all; next/font/local keeps the
 * constraint and drops the compromise. All three are SIL OFL — the licences sit
 * beside the files. */

// Mastheads, case names, and anything a person wrote. Optical sizing is left on
// so a 30px case number and a 15px diary entry get different cuts of it.
const newsreader = localFont({
  variable: "--font-newsreader",
  display: "swap",
  adjustFontFallback: "Times New Roman",
  src: [
    {
      path: "./fonts/Newsreader-latin.woff2",
      weight: "300 700",
      style: "normal",
    },
    {
      path: "./fonts/Newsreader-latin-italic.woff2",
      weight: "300 700",
      style: "italic",
    },
  ],
});

// Every label, control and table header. Franklin Gothic is the voice of a
// legal notice, which is the register the machinery wants.
const franklin = localFont({
  variable: "--font-franklin",
  display: "swap",
  src: [
    {
      path: "./fonts/LibreFranklin-latin.woff2",
      weight: "300 800",
      style: "normal",
    },
    {
      path: "./fonts/LibreFranklin-latin-italic.woff2",
      weight: "300 800",
      style: "italic",
    },
  ],
});

// CINOs, filing numbers, dates in columns. They are the spine of the app and
// they align.
const register = localFont({
  variable: "--font-register",
  display: "swap",
  src: [
    {
      path: "./fonts/SplineSansMono-latin.woff2",
      weight: "300 700",
      style: "normal",
    },
  ],
});

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    /* suppressHydrationWarning because the head script sets data-theme on this
       element before React ever sees it. */
    <html
      lang="en"
      className={`h-full ${newsreader.variable} ${franklin.variable} ${register.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Runs while the HTML is still parsing, so the right palette is in
            place before the first paint and nobody sees a white flash on the
            way into dark mode. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
