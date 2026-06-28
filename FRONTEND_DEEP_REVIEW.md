# Frontend Deep Review — computed-layout & runtime bug sweep

_Date: 2026-06-28 · Branch: `main` · Companion to [`FRONTEND_DESIGN_REVIEW.md`](FRONTEND_DESIGN_REVIEW.md) (design-consistency) and [`BACKEND_FRONTEND_PARITY.md`](BACKEND_FRONTEND_PARITY.md) (coverage)._

## Why this review exists

The design-consistency review read source for *token/component correctness* ("does it use `dxr-tbl`, the right pill, a logical prop"). That lens **structurally cannot** see a bug like the sidebar's phantom horizontal scrollbar, because nothing was wrong with the tokens — the bug only exists in **computed CSS** (`overflow-y: auto` forces `overflow-x` to `auto`; an absolutely-positioned `whitespace-nowrap` tooltip then created scroll range). A different review angle was needed.

This review is **bug-class-oriented**: each reviewer is an expert in one *failure mode* and sweeps the entire frontend for it, reasoning about what the browser renders and what the app does at runtime — not whether the source looks idiomatic. Every finding below was verified against source before reporting; low-confidence and false positives were dropped.

## The repeatable method (run this to catch "problems like it")

Seven sweeps, each a grep-for-the-smell → read-to-confirm → rate-severity-and-confidence pass:

| # | Sweep | The question it asks | Tell-tale greps |
|---|---|---|---|
| 1 | **Computed layout & scroll** | What scrolls / overflows / collapses when rendered? | `overflow-`, `whitespace-nowrap`, `absolute`/`fixed`, `min-w-0`, `grid-cols-`, `h-screen`/`min-h-screen`, `sticky`, `w-[` |
| 2 | **RTL at the computed level** | What does an Arabic user see mirrored wrong? | `ml-/mr-/pl-/pr-/left-/right-/text-left/space-x-`, `ChevronRight`/`ArrowRight`, `side=`, inline `left:/right:` |
| 3 | **White-label runtime** | What breaks when the tenant's color ≠ default? | hex literals, `text-white`+`bg-brand`/`bg-primary`/inline color, `linear-gradient(..,${x},${x})`, `color-mix`, `${hex}14` |
| 4 | **State integrity / honesty** | Where does the UI show something false? | `.catch(()=>set…([]))`, `?? true`, `window.alert/confirm`, `toast.success(t('…label…'))`, hardcoded "rows" |
| 5 | **i18n & formatting** | What stays English / mis-formats per locale? | quoted JSX text, `placeholder=`, `tt(`, `toLocaleString`, `new Date(`, `⃁`, `prefix=`, fixed `w-` on `t()` output |
| 6 | **Responsive / touch / a11y** | Does it work on a phone/tablet/wall, for keyboard & SR? | `h-7/h-8/h-9 w-`, glyph buttons, `type="checkbox/radio"`, `text-xs`, `title=` w/o `aria-label`, raw `div` modals |
| 7 | **(meta) Dead-code landmines** | What's unused now but will misrender when wired up? | exports with no importers |

Re-running these seven sweeps after any significant UI change is the durable safeguard the user asked for. The grep column is the entry point; the value is in reading the surrounding JSX to confirm a *real* mis-render, not a style nit.

---

## Findings

> Scope-wide good news first: the codebase is **well-migrated** for several of these classes. Sweep 1 found the app shell already carries the exact overflow fix (now with a comment) and `truncate` sites pair with `min-w-0`. Sweep 2 found **zero** physical `ml/mr/pl/pr`, no `space-x`, correct forced-LTR fields. The remaining issues are concentrated, not pervasive.

### CRITICAL — non-English users get a half-English app

**C1 · 144 i18n keys missing from `hi` and `ur`.** Programmatic diff: `en`=990, `ar`=990, **`hi`=846, `ur`=846** — the same 144 keys absent from both (`lib/i18n.ts`). `translate()` falls back to English, so Hindi/Urdu users see English across **checkout** (`refund`, `pay`, `clear`, `discount`), the **entire ZATCA onboarding wizard**, **Store Settings / business hours**, the **receipt-template designer**, and the **billing/quota/Moyasar** block. _Fix: backfill the 144 keys into `hi` and `ur`._

**C2 · ~139 `tt(key, 'English')` fallback keys exist in NO locale map** — so they render English for **ar/hi/ur alike**, silently un-localizing whole pages: `UserProfile` (effectively English-only), `BranchManagement`, `CategoryManagement`, `CustomerManagement`, `ExpenseTracking`, `LoyaltyProgram`, `NotFound`, and the MasterDashboard "Needs Attention"/health area. _Fix: promote each `tt()` fallback to real keys in all four maps; the `tt` fallback is masking missing translations instead of surfacing them._

> Together C1+C2 ≈ **283 strings effectively English** for non-English users — the single biggest finding in either review. (Note: per the 2026-06-18 product decision, Western digits in Arabic are intentional and `toArabicDigits` is a no-op, so digit localization is _not_ a defect — these text gaps are.)

### HIGH — visible breakage for real tenants / users

**H1 · `AgentLandingPage.tsx` paints `text-white`/`#fff` on the agent's own chosen brand color in 7 places** (lines 320, 344, 362, 385, 418, 502, 518) with **no contrast guard**. An agent who picks a pale brand gets unreadable white-on-pale CTAs on their public landing page — and `BrandingContext.readableForeground()` already exists and would pick dark ink, but this page ignores `--primary-foreground` and forces white. _Fix: drive CTAs off `bg-primary text-primary-foreground` or compute a readable foreground from `brand`; warn at color-pick time._

**H2 · `CustomerDisplay.tsx:71` uses `min-h-screen` on a standalone (non-shell) route**, so with enough line items the welcome header and the big **TOTAL footer scroll off-screen** and the cart's `overflow-y-auto` never engages (it's never height-bounded). On a passive second monitor nobody scrolls, so the amount due can be invisible to the customer. _Fix: `h-screen` (+ optional `overflow-hidden`) so the middle cart scrolls internally and the total stays pinned._

**H3 · `AgentDashboard.tsx:514` feature-override switches show fabricated state.** `featureState[f] ?? true` is never hydrated from the client's real flags and is keyed by feature name only — so every client's panel shows all features **ON**, and toggling client A then opening client B shows A's positions on B. An admin makes entitlement decisions against controls that don't reflect reality. _Fix: hydrate per-client from real flags; key state by client id; default from data, not `?? true`._

**H4 · `ClientDashboard` renders a fake all-zero dashboard on load failure** (`:50-68`; catch only `console.error`s). A backend outage looks like a real, quiet zero-sales day — no error, no retry. _Fix: set an error flag and render `ErrorState` with retry._

**H5 · POS cart touch targets are far below 44px on the most-used screen** (`POSTerminal.tsx`): line-remove is a 24px raw `✕` (`:1822`), qty steppers are 36px `-`/`+` (`:1850`), open-price/weight inputs are 24–28px (`:1810`, `:1842`). Mis-taps mid-sale on a counter tablet. _Fix: `h-11 w-11`, lucide icons + `aria-label`, `text-base`, `inputMode="decimal"`._

**H6 · Mobile nav is icon-only with no labels** (`DashboardLayout.tsx`): the drawer reuses the 80px rail and the only labels are `lg:`-only hover tooltips, so phone/tablet users face up to 26 unlabeled near-identical icons (hover doesn't exist on touch). SR users are OK via `aria-label`; sighted touch users must guess. _Fix: show text labels beside icons when the drawer is open._

### MEDIUM

- **POS sale/refund layout** (`POSTerminal.tsx:1519/1288`): same `min-h-screen`-inside-`<main overflow-auto>` mismatch as H2 — the cart's internal scroll is a no-op and the checkout block sits below the whole product grid. _Fix: bound to `lg:h-full` with the product column owning its own scroll._
- **`AgentDashboard.tsx:538` same-color "gradient"** `linear-gradient(135deg, ${b}, ${b})` + `text-white` on tenant brand in the "your white-label look" preview — invisible logo/name for a pale brand, in the very widget meant to show branding. _Fix: flatten to a fill; derive readable foreground._
- **`BrandingEditor` preview lies** (`:262/266`): forces `text-white` while the real app computes a readable foreground via `readableForeground()`, so a pale brand previews white but renders dark. Plus no contrast warning anywhere in the editor. Also `${primaryColor}14` (`:259`) assumes a 6-digit hex while a free-text field (`:172`) allows `#abc`/`red` → invalid color, and that value flows into `AgentLandingPage`'s `color-mix` derivations and can collapse them. _Fix: mirror `readableForeground` in preview; validate/normalize hex; surface a WCAG warning._
- **Six more list pages swallow load failure into "empty"** (error→empty masquerade): `ProductManagement` (main grid), `CustomerManagement` (main list), `BranchManagement`, `CategoryManagement`, `DevicesSettings`, `ExpenseTracking`, `PrinterSettings`. A failed fetch reads as "you have none." _Fix: error flag + `ErrorState`, mirroring `StaffManagement`/`ReportsAnalytics`._
- **`UserProfile.tsx:210` "Current Session / Active now" is a hardcoded fake row** under a "Security & Sessions" heading — implies session tracking that doesn't exist (and the backend endpoints for it _are_ ready per the parity audit). _Fix: wire to real sessions, or relabel so it doesn't imply live state._
- **`StoreSettings.tsx:73` success toast prints the button label** ("Save Changes") instead of a result, and `handleSave` has `try/finally` with **no catch** — a failed save shows nothing. _Fix: result string + catch with error toast._
- **CountUp currency** (`MasterDashboard.tsx:248/282`, `AgentDashboard.tsx:364`): `prefix="⃁ "` puts the glyph *before* the number while `formatMoney` puts it *after* — KPI tiles disagree with every other money string and the leading symbol is bidi-fragile in RTL. _Fix: format the string, or add a currency mode to CountUp._
- **Unmirrored directional icons in RTL**: `ChevronRight` drill-in arrows (`MasterDashboard.tsx:347/357/366`) and trailing `ArrowRight` nav arrows (`MasterDashboard:290/379`, `ClientDashboard:195/306`) point the wrong way for Arabic users — while shadcn primitives and the landing/OrderTicket pages correctly use `rtl:rotate-180`. _Fix: add `rtl:rotate-180`._
- **Native `<input type=radio/checkbox>`** in `OrderTicket.tsx:793/1031` (modifier picker, settle-by-item) — ~13–16px OS controls on a server's tablet, inconsistent with the shadcn `Checkbox`/`RadioGroup` standard. _Fix: swap to shadcn._
- **POS "Held tickets" modal is a raw `div`** (`:2192`) with no `role="dialog"`/`aria-modal`, no focus trap, no Esc — unlike every other (shadcn `Dialog`) modal. _Fix: port to `Dialog`._
- **KDS type scale too small for a wall display**: header/items `text-sm`, timer `text-xs` (`KDS.tsx:458/463/474`). _Fix: bump body to `text-base`/`text-lg`._
- **Shared `DataPagination` "of" is hardcoded English** (`components/DataPagination.tsx:28`) — appears on every paginated list; also inline in `AgentDashboard.tsx:426`. _Fix: `t('of')` / a range template key._
- **`Notifications.tsx:66` and `MasterDashboard.tsx:397` hand-roll dates** (`toLocaleString('ar-SA'…)` reintroduces Hijri+Arabic-Indic against policy; `'en-GB'` shows English months to all locales). **`Reservations.tsx:312`** shows a raw ISO datetime. _Fix: `formatDateTime(value, language)`._
- **Several POS icon-only controls have `title` but no `aria-label`** (`:1252/1261/1599/1758/2206/1892`, `KDS:498`) — `title` never shows on touch and is weak for SR; several are also sub-44px.

### LOW

- **`tracking-*` on Arabic isn't actually neutralized** (`index.css:176`): the `[dir='rtl']` base rule is out-ranked by Tailwind utilities (utilities layer always beats base), so `tracking-wider` table headers (`MasterDashboard:302`, `ClientDashboard:311`, `AgentDashboard:454`, `AuditLog:159`) insert visible gaps into Arabic cursive joins. _Fix: a utilities-layer override `[dir='rtl'] [class*='tracking-']{letter-spacing:normal}`._
- **`ReportsAnalytics` ships a private ~449-line 4-locale map** (`:41-490`) duplicating `lib/i18n.ts` — drift risk, dead `sar:'⃁'` keys. _Fix: migrate into i18n._
- **KDS "late" is color-only** (`:450`) — invisible to color-blind cooks; add an `AlertTriangle` + `t('late')` badge.
- **Segmented `dxr-seg` tabs are ~28px** on KDS/FloorMap touch contexts; **tender buttons ~34–36px** on POS checkout — under 44px. _Fix: a touch variant._
- **Single-language hardcoded placeholders**: `ProductManagement.tsx:516` (`"اسم المنتج"`), `:1120` (`"Red / Large"`), `KDS.tsx:355/367`. _Fix: localize content-bearing placeholders._
- **Truncation that clips longer ar/ur strings**: `AuditLog:184` (`max-w-[320px]`), `ExpenseTracking:342`, `ReportsAnalytics:968` (`w-24` product name). _Fix: wider caps or tooltips._
- **Dead-code landmine**: `components/dashboard/rx/SpotChart.tsx:157` has the exact phantom-scroll tooltip pattern (`absolute whitespace-nowrap` + `-translate-x-1/2`) but is **imported nowhere**. Harmless today; will misrender the moment it's wired into a single-axis-overflow tile. _Fix when used: `overflow-x-clip` on the host or constrain the tooltip offset._

---

## Prioritized fix queue

1. **C1 + C2 — i18n backfill** (283 strings). Biggest user-visible defect; ar/hi/ur are partly English today. Mostly mechanical map edits.
2. **H1 / M (white-label foregrounds)** — replace `text-white`-on-tenant-color with `text-primary-foreground` + a contrast guard (AgentLandingPage, AgentDashboard preview, BrandingEditor, POSTerminal `bg-brand` decision). Breaks public agent surfaces for any pale brand.
3. **H2 + POS height chain** — `min-h-screen` → `h-screen`/`h-full` on CustomerDisplay and POSTerminal so totals/checkout pin and inner scroll works.
4. **H3 / H4 / state masquerades** — hydrate AgentDashboard switches; add `ErrorState` to ClientDashboard + the 8 list pages that swallow failures; fix the StoreSettings toast/catch; de-fake the UserProfile session row.
5. **H5 / H6 touch & mobile** — 44px POS cart controls; labels in the mobile drawer.
6. **RTL icon mirroring + tracking override** — `rtl:rotate-180` on the unmirrored chevrons/arrows; utilities-layer Arabic letter-spacing reset.
7. **Date/formatting + pagination i18n** — route all hand-rolled dates through `formatDateTime`; localize "of"; unify CountUp currency with `formatMoney`.

## Caveat

Still a static review — verified against source and CSS-spec behavior, not a live build with screenshots and a real tenant theme. The height-chain (H2) and contrast (H1) findings especially warrant a 5-minute confirm in-browser (load a long cart on CustomerDisplay; set a pale tenant brand). The seven-sweep method above is the repeatable part; re-run it after UI changes.
