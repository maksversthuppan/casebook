# The look of it

The visual language is called **Cause List**. It borrows from the printed
matter this firm already works in: the court's cause list, the law report, the
firm's own daybook. Ruled paper, a margin down the left, numbers set in a
register hand.

None of it is decoration for its own sake. Every device below exists to make one
of `CONTEXT.md`'s distinctions visible without anyone having to read a label.

## The one idea

**The court's voice and the firm's voice never look alike.**

This system's central rule — a refresh replaces every court-sourced fact and
nothing else (rule 1, ADR-0002, ADR-0007) — is a rule about provenance. So
provenance is what the design encodes:

| | Court-sourced | Firm-authored |
|---|---|---|
| Colour | `--court`, a deep teal | `--firm`, a deep blue |
| Mark | a filled square `▪` | a pilcrow `¶` |
| Where | Court Status, Hearings from DCMS, Act & Section, Crime Details, Counsel, the CINO | Diary Entries, Notes, Tasks, Firm Status, Representation, the Vakalath |

A Hearing the court reported and a Hearing an advocate wrote down sit on the
same Timeline, on the same date, and are told apart at a glance by the colour of
the rule down their left edge. Same for the two statuses in the Status panel:
the firm's half is blue, the court's half is teal, and they are never adjacent
enough to read as one field.

Blue is also the interaction colour — focus rings, the caret, the primary
button, the active filter. That is the same idea rather than a second one: an
interaction is the firm's hand, and this application is the firm's record.

The colour is always **reinforcement, never the only signal**. Every provenance
mark carries its glyph, and every panel carries the words *The firm* or *The
court*. Turn the palette to greyscale and nothing is lost.

## Four hues, one job each

Kept far enough apart on the wheel to survive a colour-blind reader:

| Token | Hue | Means | Appears on |
|---|---|---|---|
| `--firm` | blue | the firm's own hand; every interaction | provenance rules, focus, primary buttons, active filters |
| `--court` | teal | what DCMS reported | provenance rules, Court Status, Counsel |
| `--danger` | red | irreversible or wrong | the Relinquished stamp, error banners, the relinquish confirmation |
| `--caution` | amber | missing, not wrong | a date that passed with nothing recorded against it |

Red earns its weight by being rare: it appears nowhere else in the interface, so
a Relinquished stamp is the loudest thing on any page it sits on.

## Three typefaces, three jobs

All three are vendored into `app/fonts/` as woff2 and loaded with
`next/font/local`, so the office server never reaches the internet to build or
to run — the constraint the old `layout.tsx` comment set out, kept.

- **Newsreader** (`font-display`) — mastheads, case names, and anything a person
  wrote: Diary Entries, Notes. Prose set in a reading face reads as prose. Its
  optical-size axis is live, so a 30px case number gets the display cut and a
  15px diary entry gets the text cut.
- **Libre Franklin** (`font-ui`) — every label, control, table header and
  caption. Franklin Gothic is the voice of a legal notice; that is exactly the
  register wanted for the machinery around the content.
- **Spline Sans Mono** (`font-mono`, the `.ident` class) — CINOs, filing and
  registration numbers, dates in columns, CAPTCHA input. The numbers are the
  spine of this app and they align.

## The rest of the grammar

- **Ruled, not boxed.** Hairline rules and a double rule under the masthead,
  rather than rounded cards floating on grey. Panels are announced by a rule and
  a small-caps label above them, the way a law report announces a section.
- **The margin.** Lists put the date in a fixed left column in mono and the
  content to its right. The eye runs down the dates.
- **Paper, not white.** A cool sheet — a faint blue-grey cast, the colour of
  bond paper rather than a screen — with a grain overlay at 3% and no pure
  black. Dark mode is the same stock in a slate-navy, built as its own theme
  rather than an inverted document: the accents lighten, and text laid over
  them flips to dark (`--on-accent`), because white on a light blue fill is
  2.4:1.
- **Letterpress, not elevation.** Buttons take a hard offset shadow and press
  into it on `:active`. Nothing floats; there are no blurred drop shadows.
- **Motion is a page settling.** One staggered rise on load, ~400ms, and hover
  states that slide a marker into the margin. Nothing else moves. All of it is
  off under `prefers-reduced-motion`.

## The things that must keep shouting

Design freedom stops at these; they are in `CONTEXT.md` and `ROADMAP.md` for
reasons that cost someone something.

- **Relinquished** is a stamp: filled `--danger` red, uppercase, letterspaced,
  tilted slightly, wherever the case appears. An advocate acting on a case the
  firm has given up is the damage being prevented.
- **On hold looks quiet.** It is a plain word in the ordinary ink. The firm still
  holds that case and is still answerable for it, and it must never be mistaken
  for relinquished.
- **A date that passed with nothing recorded** is `--caution`, an ochre. Not red:
  nothing is wrong, something is missing.
- **Nothing is ever "up to date".** Court-sourced data is shown as *confirmed on*
  a date, and a case nobody has refreshed lately is *unconfirmed*, never *stale*
  in the user-facing wording.
- **Apply-whole-or-discard-whole.** The refresh diff has exactly two buttons and
  no per-row control, and the page says so before it lists anything.

## Choosing a theme

Light, **system** (the default) and dark, as three buttons in the masthead —
and a second copy on the sign-in screen, which sits outside the app shell.

A two-state switch was the obvious thing and is the wrong one: it cannot say
"follow the OS", which is what most people will leave it on. The stored value is
the *preference*; `data-theme` on `<html>` is always a resolved `light` or
`dark`.

- The resolution happens in an inline script in `<head>` (`THEME_INIT` in
  `app/components/Theme.tsx`), which runs while the HTML is still parsing. That
  is what stops a white flash on the way into dark mode — `useEffect` runs after
  paint and `useLayoutEffect` after hydration, both too late.
- Because the script resolves "system" itself, `globals.css` holds each palette
  **exactly once**. There is no `prefers-color-scheme` block duplicating the
  dark values, and so no way for the two to drift.
- The preference is read with `useSyncExternalStore`, not mirrored into state
  from an effect, so the server render and the hydration render agree.
- On "system" the app keeps tracking the OS live via a `matchMedia` listener,
  rather than reading it once at load.
- Each palette declares `color-scheme`, so native scrollbars, form controls and
  the date picker's own icon follow the **chosen** theme. This replaced a
  hand-rolled `filter: invert()` on the date picker that keyed off
  `prefers-color-scheme` — correct until the theme could disagree with the OS,
  at which point it inverted the wrong way.

There is deliberately no no-JS fallback: every screen is a client component that
fetches its own data, so without JavaScript there is nothing to theme.

## Tokens

Defined once in `app/globals.css` under `:root`, re-declared under
`prefers-color-scheme: dark`, and exposed to Tailwind through `@theme inline`,
so `text-court`, `border-rule`, `bg-firm-wash` and friends work and follow the
theme automatically.

Three weights of line, and the distinction is not cosmetic:

- `--rule` — hairline separators between rows. Decorative, so no contrast floor.
- `--rule-strong` — the section and masthead rules. Also decorative.
- `--edge` — the boundary of an actual control: inputs, selects, outlined
  buttons. Clears **3:1** in both themes, because WCAG 1.4.11 applies to the
  thing that tells you where a text field is. Using `--rule` here left inputs
  effectively invisible at 1.3:1, which is what prompted splitting the token.

## What was measured

Contrast was computed, not judged by eye, for every foreground/background pair
in both themes. Body and label text clears **4.5:1**; control edges clear
**3:1**; text on solid `--firm` / `--danger` fills clears 6.5:1 in light and
7.8:1 in dark. `scripts/`-free check: the ratios live in the ROADMAP entry for
2026-08-10 if they need re-deriving.

Two related fixes came out of the same pass: `.field-input` had `outline: none`
on `:focus`, which removed the keyboard ring for everyone, so a `:focus-visible`
rule now restores it; and inputs render at 16px below the `sm` breakpoint,
because anything smaller makes iOS zoom the page on focus.
