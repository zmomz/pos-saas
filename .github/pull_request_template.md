<!--
  Keep this PR description short and honest. The checklist below is the
  pre-merge deep-review 7-sweep gate — see .github/REGRESSION_CHECKLIST.md.
-->

## What & why

<!-- One or two sentences. Link the issue: "Closes #NNN". -->

## Pre-merge regression sweeps

Run the seven deep-review sweeps from
[`.github/REGRESSION_CHECKLIST.md`](.github/REGRESSION_CHECKLIST.md) against this
change. Tick each, or mark **n/a** for a non-UI PR (`i18n-key-parity` is enforced
in CI regardless).

- [ ] `fabricated-state` — no invented/default-on data; UI reflects real backend state
- [ ] `swallowed-errors` — failed fetch/save shows an honest error+retry, never a fake "empty" or silent success
- [ ] `i18n-key-parity` — ar/hi/ur not short of `en`; no `tt()`/JSX-literal English leaks _(CI-enforced)_
- [ ] `contrast` — readable on any tenant brand color; contrast guard, no forced `text-white`, valid hex
- [ ] `height-touch` — pins totals (no `min-h-screen` traps), ≥44px controls, labeled mobile nav
- [ ] `table-voice` — shared table voice + shared empty/error/loading states; shadcn primitives & dialogs
- [ ] `currency-date` — money via `formatMoney`, dates via `formatDateTime`; no per-page locale maps

## Tests

<!-- What you added/ran. CI runs lint · typecheck · unit (coverage ratchet) · build · e2e. -->
