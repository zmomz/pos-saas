# Project Addendum — Cloud POS stack

Local extension to the `frontend-design` skill. The upstream `SKILL.md` is
stack-agnostic; this file pins design work to **this** repo's system so output
stays consistent with the existing app. When the two conflict, the upstream
principles still govern _taste_; this file governs _mechanics_.

Root: `frontend/` · React 18 + Vite + TypeScript · Tailwind (no class prefix) ·
shadcn/ui (Radix) · path alias `@/` → `frontend/src`.

---

## 1. Non-negotiables (break these and the app breaks)

- **Never hardcode the brand/primary color.** It is **white-labelled at runtime**:
  `contexts/BrandingContext.tsx` → `applyBranding()` rewrites `--primary`,
  `--ring`, `--primary-foreground`, `--accent`, `--radius`, and the body font per
  tenant. Always go through the token: `hsl(var(--primary))`, Tailwind
  `primary` / `brand` / `accent` utilities. A literal hex for the primary will be
  wrong for every agent/client but the default one.
- **Direction-agnostic layout only.** App runs **LTR and RTL** (ar, ur).
  `document.documentElement.dir` is flipped in i18n. Use **logical** utilities —
  `start-*`/`end-*`, `ms-*`/`me-*`, `ps-*`/`pe-*`, `text-start`/`text-end`,
  `border-s`/`border-e` — **never** `left/right`, `ml/mr`, `pl/pr`. Mirror
  directional icons (chevrons, arrows) with `rtl:-scale-x-100` when meaningful.
- **All user-facing copy goes through i18n.** `lib/i18n.ts`, hook `t()`. Four
  locales: **en, ar, hi, ur**. Every new string needs a key in **all four** maps.
  Bilingual content fields are paired (`name` + `name_ar`); keep that pattern for
  any new merchant-authored content.
- **Currency.** Prices render the Saudi Riyal glyph (U+20C1) automatically — the
  `'Saudi Riyal'` webfont leads every font stack via `unicode-range`. Use
  `formatMoney` / `formatMoneyAr` from `lib/format.ts` (and `formatNumber`,
  `formatDate`, `toArabicDigits`). Don't hand-roll currency strings or add a `SAR`
  text suffix. If you introduce a new font stack, `'Saudi Riyal'` must stay first.

## 2. Design tokens (the palette is already decided)

Identity = **petrol teal-blue + warm gold**. Light + dark (`darkMode: 'class'`,
`.dark` on root). Defined in `src/index.css` (`:root` / `.dark`), exposed via
`tailwind.config.ts`.

- **Primary / brand:** `--primary` (petrol teal-blue, `#1488a6`). Scale
  `brand-50…900`. This is the single primary across all surfaces.
- **Accents:** `gold` (`#e6b45c`, dark ink `gold-900`), `cyan` (`var(--cyan)`,
  `#36c5e0`) for dark tiles / gauges / spark lines.
- **Semantic (fixed across themes):** `success`, `warning` (needs **dark** ink
  foreground, not white), `danger`, `violet`, `sky`. Each has a `foreground`.
- **Surfaces:** `background`, `card`, `popover`, `muted`, `border`, `input`,
  `ring`, plus a dedicated `sidebar-*` group (deep petrol + gold active marker).
- **Radius:** base `--radius: 0.75rem`; use `rounded-lg/xl/2xl` (derived).
- **Shadow:** `shadow-card` (resting cards), `shadow-brand` (hero/brand lift).
- **Motion:** `animate-fade-up`, `animate-float`, accordion in/out are defined —
  reuse before inventing keyframes. Keep motion purposeful (see upstream skill).

Taking "one real aesthetic risk" (per the skill) is welcome — but express it
through **these** tokens and the dark-`dxr-ink` tile language, not a new palette.

## 3. Reuse the component vocabulary before building new

- **shadcn/ui** primitives live in `components/ui/` (button, card, dialog, sheet,
  drawer, table, tabs, select, command, sonner/toast, sidebar, input-otp, …).
  Compose these; do not re-implement primitives or pull a new UI library.
- **House component classes** (in `index.css`, the `dxr-*` "design-handoff"
  language) — prefer these for dashboard surfaces:
  - Status pills: `pill-success | pill-danger | pill-warning | pill-violet |
    pill-sky | pill-muted | pill-gold`.
  - Tiles/cards: `surface-panel`, `dxr-tile`, `dxr-hover`, `dxr-ink` (dark tile),
    `dxr-eyebrow` (label/kicker).
  - Segmented controls: `dxr-seg` / `dxr-seg-ink` (`button[data-active='true']`).
  - Icon swatches: `dxr-sw` + `dxr-sw-{brand,success,violet,sky,gold,warning,danger}`.
  - KPI deltas: `dxr-delta` + `dxr-delta-{up,down,flat}`; `dxr-insight`.
  - Tables: `dxr-tbl`. Gradients/text: `brand-gradient`, `brand-text-gradient`.
- **Shared states** in `components/states/`: `LoadingState`, `EmptyState`,
  `ErrorState`, `NotFoundState`, `PermissionDenied`, `OfflineBanner`. Every async
  view should render these three states (loading / empty / error) — match the
  existing pages (e.g. `ZatcaStatus.tsx`).

## 4. Page scaffolding

- Authenticated pages render inside `components/DashboardLayout.tsx`: a fixed
  **icon-rail sidebar** + a shared **⌘K command bar** (`PageChromeContext`).
- A page declares its chrome with **`usePageChrome({ subtitle, actions, … }, deps)`**
  — primary action button + page-specific ⌘K quick actions. Use it instead of
  rendering bespoke page headers.
- Theme + branding come from context (`ThemeContext`, `BrandingContext`); read
  them, don't re-fetch.

## 5. Quick checklist before finishing any UI change

- [ ] No `left/right`/`ml`/`pl` — logical props only; looks right in **RTL**.
- [ ] No hardcoded primary hex — uses `primary`/`brand`/`hsl(var(--primary))`.
- [ ] New copy added to **all four** i18n locales (en/ar/hi/ur).
- [ ] Money via `formatMoney*`; SAR glyph intact; font stack still leads with `'Saudi Riyal'`.
- [ ] Verified in **light and dark**; `warning` text uses dark ink.
- [ ] Loading / empty / error states present via `components/states/`.
- [ ] Built from `components/ui/` + `dxr-*` classes; no new primitives or libraries.
