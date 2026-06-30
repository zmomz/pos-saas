# Pre-merge regression checklist — the deep-review 7-sweep

This codifies the frontend deep review's repeatable method (see
[`FRONTEND_DEEP_REVIEW.md`](../FRONTEND_DEEP_REVIEW.md)) into a standing
pre-merge gate, so the honesty / i18n / contrast regressions that review found
**cannot quietly reappear**. Run the seven sweeps against any PR that touches UI;
tick each in the PR template. Each sweep is a _grep-for-the-smell → read-to-confirm_
pass — the grep is the entry point, the value is reading the surrounding JSX to
confirm a real mis-render, not a style nit.

> Slugs (e.g. `fabricated-state`) are the contract: the PR template surfaces each
> as its own checkbox, and `frontend/src/lib/regressionChecklist.test.ts` asserts
> the checklist and template stay in sync. Don't rename a slug without updating both.

| # | Sweep | The question it asks | Tell-tale greps |
|---|---|---|---|
| 1 | `fabricated-state` | Does the UI ever invent data the backend didn't send? | `?? true`, `?? []` on real data, hardcoded "rows"/sessions, default-on toggles not hydrated from flags |
| 2 | `swallowed-errors` | Does a failed fetch/save masquerade as "empty" or silent success? | `.catch(()=>set…([]))`, `catch` that only `console.error`s, `try/finally` with no `catch`, `toast.success(t('…button-label…'))` |
| 3 | `i18n-key-parity` | What stays English / un-localized for ar/hi/ur? | missing keys vs `en`, `tt(key, 'English')` fallbacks, quoted JSX text, `placeholder=` literals (**automated**, see CI below) |
| 4 | `contrast` | What breaks when the tenant's brand color ≠ default? | `text-white`/`#fff` on `bg-brand`/`bg-primary`/inline color with no contrast guard, `linear-gradient(..,${x},${x})`, unvalidated hex → broken `color-mix` |
| 5 | `height-touch` | Does it fit a phone/tablet/wall and survive a fat finger? | `min-h-screen` on standalone routes (totals scroll away), sub-44px controls (`h-7/h-8/h-9 w-`), glyph buttons, icon-only nav with no labels |
| 6 | `table-voice` | Do tables/lists speak one shared voice (states, primitives)? | raw `<table>` not on the shared `dxr-tbl` voice, native `<input type=checkbox/radio>` vs shadcn, raw `div` modals (no `role="dialog"`/Esc/focus-trap), bespoke empty/error/loading instead of shared states |
| 7 | `currency-date` | Do money & dates format consistently per locale? | hand-rolled `toLocaleString`/`new Date(` instead of `formatMoney`/`formatDateTime`, `prefix="⃁ "` (symbol before number), raw ISO datetimes, private per-page locale maps duplicating `lib/i18n.ts` |

## How each sweep is enforced

- **`i18n-key-parity` is automated and CI-enforced** — `frontend/scripts/check-i18n-parity.mjs`
  fails the build (and runs as its own `pnpm run i18n:check` CI step) when any
  locale is short of `en`; `frontend/src/lib/i18n.parity.test.ts` mirrors it in
  unit tests. This is the gate built in #196.
- **The other six are reviewer sweeps** — run them by hand (or with a focused
  review agent) and tick the PR template. Promote any one to automation as a
  lint rule or test when a repeatable grep proves reliable.

## When to run

Any PR that adds or reshapes UI. A pure backend / docs / tooling PR can mark the
six manual sweeps **n/a** in the template, but `i18n-key-parity` always runs in CI.
