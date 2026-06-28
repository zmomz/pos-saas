# Frontend Design Review

_Date: 2026-06-28 · Branch: `main` · Method: design-led review of all five interface tiers against the `frontend-design` skill + the Cloud POS stack addendum (`references/cloud-pos-stack.md`) and the token system in `index.css`. Companion to [`BACKEND_FRONTEND_PARITY.md`](BACKEND_FRONTEND_PARITY.md)._

## Question

Across every interface — master landing/dashboard, agent landing/dashboard, the
white-label branding editor, and the client (merchant) dashboards and operational
tools — is the design **deliberate, consistent, white-label-correct, and
direction-agnostic**, or does it read as templated / assembled by different hands?

## Headline

**The design system itself is strong and the _atoms_ are excellent; the _molecules_ are where it fractures.** The petrol-teal + gold token language (`index.css`), the `dxr-*` bento/tile vocabulary, the `pill-*` status set, `StatTile`, `PageHeading`, and the shared `components/states/*` give the app a real, cohesive identity. Token discipline is genuinely good: **no page hardcodes the runtime `--primary`** onto chrome, and RTL/logical-prop hygiene is the single strongest cross-cutting win (the retail tier is clean of physical `left/right/ml/pl` props entirely).

The weaknesses are **consistency-of-adoption and hierarchy**, not palette:

1. **Shared states are optional in practice.** The `components/states/*` set is good, but a dozen pages roll their own `animate-pulse` spinners and empty blocks instead — sometimes in the same file that correctly imports `ErrorState`.
2. **No single table voice.** One product (a data list) renders five different ways: `<DataTable>`/`.dxr-tbl`, two flavors of hand-rolled `<table>`, the shadcn `<Table>` primitive, and a fourth dashboard variant.
3. **Hand-rolled currency leaks.** `formatMoney*` is near-universal, but animated count-ups (`CountUp prefix="⃁ "`), price deltas, and select-option prices bypass it — losing Arabic-Indic digits and grouping in RTL builds.
4. **The client dashboard does not adapt to business type** (restaurant vs retail) despite full API + i18n support — the biggest conceptual gap.
5. **The shell demotes page identity to a greeting**, and a 27-item icon rail doesn't scale.

None of these are token violations; they're under-adoption of systems that already exist. The fixes are mostly migration, not redesign.

---

## Tier-by-tier

### 1. Master tier — `LandingPage.tsx`, `MasterDashboard.tsx`

**MasterDashboard is the high-water mark of the app.** A real 12-col bento with a single dark `dxr-ink` MRR spotlight as focal point, token-disciplined avatar gradients (explicit "no raw hex" comment), a genuinely good "needs attention" triage rail with a graceful empty state, and `animate-fade-up` motion that conveys data rather than decorates.

- _Weaknesses:_ the top-level loader is a bare `animate-pulse` string while the leaderboard below it uses the shared `ErrorState` — the page contradicts itself (`MasterDashboard.tsx:229`). The `ecoError` only reaches the leaderboard, so the headline MRR and KPI chips silently render `⃁ 0` on failure (`:201/247/282`). The `dxr-ink` hero reserves ~150px that holds only "Trend history not available yet" — the most prominent surface reads half-empty (`:255`). Hand-rolled `CountUp prefix="⃁ "` (`:248/282`) and a hardcoded `toLocaleString('en-GB')` date (`:397`) bypass `formatMoney*`/`formatDate`. Packages cards drop `dxr-tile` for plain cards (`:422`).

**LandingPage** (a reseller-recruitment brochure) is mostly deliberate, rescued from a templated split-hero by one strong idea: the **dual-brand mockup** showing "your brand" next to a deliberately different green "another agent" brand — a literal visualization of white-label no template ships (`LandingPage.tsx:446`).

- _Weaknesses:_ two **physical-prop violations** of the direction-agnostic rule — `right-1/2`/`left-1/2` (`:493`) and `left-1/2 -translate-x-1/2` (`:518`). Magic-number typography with no display face or scale (`text-[40px]`, `rounded-[9px]/[11px]/[18px]`). Hand-rolled latin-digit prices + literal `⃁` (`:383/522`) that stay Western in ar/ur. A "Live" label + success dot over a **static** SVG (`:379/246`). No entrance motion despite `animate-fade-up` being available.

### 2. Agent tier — `AgentLandingPage.tsx`, `AgentDashboard.tsx`, `BrandingEditor.tsx`, `PackageManagement.tsx`

**AgentDashboard** is the strongest agent-tier page — full bento `dxr-*` adoption, every async section has loading/error/empty, clean RTL. Its brand fallback `#1488a6` correctly feeds only the white-label _preview_, not chrome.

- _Weaknesses:_ a **redundant bespoke header** (`:345`) duplicates the `usePageChrome` subtitle + primary action the stack says to use, giving "Run billing" two entry points. **Three table treatments, none `dxr-tbl`.** `CountUp prefix="⃁ "` spotlight (`:364`) disagrees with the `formatMoney` KPI tiles right below it. Untranslated `"{n} of {m}"` (`:426`). A **same-color "gradient"** `linear-gradient(135deg, ${b}, ${b})` (`:538`). Feature-override switches default to `?? true` and never hydrate from real flags (`:514`) — the control looks authoritative but shows fiction.

**AgentLandingPage** (the customizable, per-reseller white-label brochure) gets the theming model _right_ — themes off one `brand` variable via inline style + `color-mix` derived shades, with a sensible neutral default — and has a distinctive fake-POS-terminal mockup with a floating ZATCA QR badge.

- _Weaknesses:_ pricing cards use hand-rolled `⃁`-prefixed strings instead of `formatMoney` (`:416/491`). **Any failure routes to `NotFoundState` "Distributor Not Found"** — a transient network error tells a real agent's customer the agent doesn't exist (`:245/263`). A hardcoded `<br/>` in the headline wraps badly across four locales (`:357`). It forces `text-white` on every brand CTA with no contrast guard — a pale brand → invisible buttons. `secondary_color` is collected by the editor but never used here.

**BrandingEditor** has the right form-left/preview-right split and a live preview that sells the feature — **but the preview lies about fonts:** it offers Inter/Roboto/Poppins/Cairo/Noto, none of which are bundled, so `fontFamily` silently falls back to system (`:18/244`). Plus hardcoded English toast strings (`:65/117/120`), no contrast guard at the exact place colors are picked, and a Latin-only pangram that gives Arabic-first agents no sense of their font.

**PackageManagement** has the best state coverage of the tier but the flattest visuals, and a real copy bug: a button labeled `deactivate` that calls `handleDelete` → actually deletes (`:206/122`).

### 3. Client dashboard + retail CRUD — `ClientDashboard`, `Product/Customer/Staff/Supplier/Discount Management`, `ReportsAnalytics`

**ClientDashboard** has a genuinely considered hero: a `dxr-ink` "Today's Sales" spotlight with a **real sparkline computed from actual transactions** (`:134/182`) and a brand-gradient "Open POS" tile — one clear point of view, token-correct, white-label-safe.

- _Biggest gap:_ **it does not adapt to `business_type` at all.** `business_type ∈ {retail, restaurant, both}` is a first-class field with i18n already written (`lib/i18n.ts:639`), yet a restaurant merchant gets the identical retail "Avg Ticket / Products" framing — no covers, tables, or menu language. The page doesn't even fetch the profile. _Also:_ raw `subscription_status` printed as snake_case (`:241`), hand-rolled currency count-up, hand-rolled transactions table, bespoke loader.

**Retail CRUD consistency** — the atoms are uniform (`StatTile`, `PageHeading` + `dxr-sw-brand` icon, `pill-*` statuses, zero physical CSS props). The molecules fracture:

- **Five table voices for one job** (see Headline #2). The `DataTable` docstring says it exists to replace the hand-rolled tables — that migration is half-done (Product/Supplier migrated; Customer/Staff/Discount/Reports/dashboard not).
- **Two tiers of error robustness:** Staff/Supplier/Discount correctly split `denied`/`error`/empty; **Product, Customer, and the Dashboard silently swallow load failures into an empty list** (`ProductManagement.tsx:223`, `CustomerManagement.tsx:109`) — the UX-02 masquerade the others were hardened against.
- **Inconsistent toolbars:** icon-prefixed search (Customer/Supplier) vs plain no-icon input (Product) vs no search (Staff/Discount).
- White-label nit: `bg-brand text-white` filter chips in Customer (`:481`) should be `text-primary-foreground`.
- `lg:grid-cols-4` with only 3 `StatTile`s leaves a dangling empty column (Customer/Staff/Supplier).
- `ReportsAnalytics` carries a **489-line private translation map** (`:41-490`) duplicating `lib/i18n.ts` — a maintenance island with `sar: '⃁'` baked in.

### 4. Restaurant + POS operational surfaces — `POSTerminal`, `KDS`, `OrderTicket`, `FloorMap`, `MenuBuilder`, `Reservations`, `CustomerDisplay`

**The in-layout restaurant pages cohere well** — `PageHeading` + `dxr-sw`, `animate-fade-up`, `dxr-seg`/`dxr-tile`, `pill-*`, and proper states. **Reservations is the model citizen** (actually uses `ErrorState`/`PermissionDenied`/`OfflineBanner`). **FloorMap** has textbook state color-coding from a single source of truth. **CustomerDisplay** nails distance type scale (`text-3xl`–`text-5xl`) and has a real "paid" moment.

**The two fullscreen tools (POSTerminal, CustomerDisplay) read as an older, separate generation** — partly justified (they live outside `DashboardLayout`), but the divergence is larger than needed:

- **White-label violation:** `text-white` on `bg-brand` across the checkout button, category chip, cart badge, split toggle (`POSTerminal.tsx:1545/1685/1712/2004/2175`) — a pale tenant primary gives invisible text. Use `text-primary-foreground`.
- **Sub-44px tap targets on the most-used screen:** 24px `✕` remove, `h-9 w-9` qty steppers (`:1822/1854`).
- **Emoji as UI** (`✓ ✕ ↩`) and a raw `window.alert` in OrderTicket (`:342`) vs the app's lucide + sonner standard.
- **KDS type scale is too small for a wall display** — title/items `text-sm`, timer `text-xs` (`KDS.tsx:458/474`); and lateness is binary (a 9-min ticket looks fresh) when an amber middle tier and bigger type would transform glanceability. This is the highest-value restaurant fix.
- CustomerDisplay falls back to the platform name `'POS System'` (`:18`) with no logo — a customer-facing screen leaking the SaaS brand.
- Status-as-tint (`bg-brand-500/x text-brand-600`) instead of `pill-*` tokens in FloorMap/Reservations/KDS.

### 5. Auth + shell — `Index`, `ForceResetPassword`, `DashboardLayout`, `components/states/*`

**DashboardLayout** is RTL-correct by construction (logical props, drawer transform branches on `isRTL`) with a confident brand-gradient active state. Two structural problems:

- **The H1 is the greeting, on every page.** "Good morning, Zeyad" is the biggest text on Reports and Store Settings alike; page identity is demoted to a 13px subtitle (`:320`). The frame should announce the page.
- **27 undifferentiated icons in an 80px scrolling rail** with no sections and reused icons (`Receipt` for expenses _and_ receipt_template; `Package` for packages _and_ catalog_modifiers). Labels exist only as hover tooltips — which don't exist on touch, so the mobile drawer is an icon guessing-game.

**components/states/** is a genuinely consistent, a11y-aware family (the `OfflineBanner` even carries the queued-sales count — a real POS detail). But it's **neutral, not branded** — default lucide icons, none speak `dxr-*`, and the icon treatment is itself inconsistent (EmptyState badges its icon; Error/Permission float a bare one). And it's under-adopted: `Index.tsx:53` and `Notifications.tsx:98-113` hand-roll loading/empty right next to the shared components.

**Index (login) is a templated auth screen, not a thesis** — stacked fields, full-width button, an underlined-text register toggle that reads as a footnote. The petrol identity lives in `AuthLayout` but the composition takes no aesthetic risk for the product's first frame. No password-visibility toggle, no forgot-password link (the latter also flagged as a backend-ready gap in the parity audit, item #3).

---

## Cross-cutting themes (priority order)

1. **Adopt the shared `states/*` everywhere.** Replace bespoke `animate-pulse` spinners and empty blocks in `Index`, `Notifications`, `MasterDashboard`, `AgentDashboard`, POSTerminal, ClientDashboard, etc.; add `LoadingState` to `StoreSettings`/`UserProfile` form fetches. Pure migration — the system already exists and is good.
2. **One table voice.** Migrate Customer, Staff, Discount, Reports, and the dashboard transactions onto `<DataTable>`/`.dxr-tbl`. Finish the migration the `DataTable` docstring already promises.
3. **Close the silent-error masquerade.** Bring Product, Customer, and ClientDashboard up to the Staff pattern (distinct `denied`/`error`/empty) — never render an empty list on a load failure.
4. **Currency through `formatMoney*` everywhere.** Kill `CountUp prefix="⃁ "`, raw price deltas, and select-option prices (Master/Agent/Client dashboards, OrderTicket, MenuBuilder). Route dates through `formatDate` (Notifications, Reservations, MasterDashboard).
5. **Make ClientDashboard business-type aware.** Fetch the profile; reframe the hero metric and quick-actions for restaurant vs retail. Fully supported by existing API + i18n.
6. **Fix the shell hierarchy.** Page name → H1; greeting → dashboard home only. Section the 27-item client rail (Sell / Catalog / People / Setup) and show labels in the mobile drawer.
7. **Add a white-label contrast guard.** Anywhere `text-white` sits on `bg-brand`/tenant color (POSTerminal, Customer chips, AgentLandingPage CTAs, BrandingEditor preview), switch to `text-primary-foreground` and warn/auto-flip when a pale brand is chosen.
8. **Close i18n leaks:** hardcoded English day names (`StoreSettings:191`), `tt(…, 'English')` inline fallbacks (`UserProfile`), toast strings (`BrandingEditor`), `"of"` (`AgentDashboard`), and the 489-line private map in `ReportsAnalytics`.
9. **Two targeted upgrades where the app reads most templated:** give **Index/login** a real composition (brand/`dxr-ink` panel + product thesis), and give **KDS** a wall-display type scale + 3-tier lateness color.
10. **Truthful affordances:** `deactivate` that deletes (`PackageManagement:206`), BrandingEditor's unbundled font list, AgentDashboard's always-on feature switches, and UserProfile's single hardcoded "session" row all _look_ authoritative but misrepresent state.

## Two correctness bugs surfaced en route (not just aesthetic)

- `LandingPage.tsx:493/518` — physical `left/right` props break the RTL layout the addendum forbids.
- `AgentLandingPage.tsx:245` — transient API errors render `NotFoundState` "Distributor Not Found" to a reseller's prospective customers.

## Relationship to the parity audit

The parity audit found **missing UI for backend-ready features**; this review finds the **opposite class of problem** — UI that exists but is visually inconsistent or misrepresents state. They reinforce each other in two places: the **forgot-password** flow (parity #3) is also the login screen's most visible omission, and **profile/session management** (parity #2, #4) is exactly the UserProfile "Security & Sessions" row that currently shows one static fake entry.

## Caveat

This is a **design/consistency** review read from source (composition, hierarchy, token/state adoption, RTL, i18n, white-label correctness). It was not run against a live build with screenshots, so it does not certify pixel rendering, real contrast ratios per tenant theme, or animation timing. A screenshot pass in light + dark + one RTL locale would close that gap.
