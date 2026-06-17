# Design Consistency Audit & Remediation Plan
**Scope:** Master / Agent / Client (POS) dashboards and all back-office pages
**Reference design system:** `creative_redesign/` (`ds.css`, `master.html`, `agent.html`, `client.html`)
**Live tokens:** `frontend/src/index.css` · **Live shell:** `frontend/src/components/DashboardLayout.tsx`
**Date:** 2026-06-17

---

## Core finding

The *"roll the bento design system out to every back-office page"* work was applied as a
**re-skin (tokens + `dxr-*` classes), not a system migration**. Every page wears the petrol/gold
palette, but the underlying *structure* — shell, cards, tables, headers, buttons, states — fragmented
into **two or three competing implementations of everything**.

The reference (`creative_redesign/`) is a coherent system: 80px **icon rail** + **⌘K command bar** +
12-col **bento grid** + dark **"ink" spotlight tiles** + one table style + one pill set. Almost none of
that structure actually shipped.

There are ~9 systemic problems below. Fixing those ~9 things resolves the large majority of the ~120
individual findings.

---

## Systemic problems (ranked by impact)

### 1. [Critical] The shell never made the redesign
- `DashboardLayout.tsx:131` is still a **256px labeled sidebar** with a thin utility header.
- Reference is an **80px icon rail** (`ds.css:92-123`) + **command bar** with greeting, ⌘K search,
  notification bell, primary action (`master.html:35-48`). None of that is in the shared shell.
- The **⌘K palette (`CommandPalette`) is mounted only in MasterDashboard** — Agent and Client have no
  command bar at all, so each dashboard fakes its own top chrome → all three differ.

### 2. [Critical] Two generations of components — four are orphaned dead code
Verified by import graph:

| Component | Status |
|---|---|
| `dashboard/StatCard.tsx` | **Orphaned** — imported nowhere; uses raw `emerald/amber/sky/rose` Tailwind (the exact banned non-token colors) |
| `dashboard/MrrTrendChart.tsx` | **Orphaned** — superseded by `rx/SpotChart` |
| `dashboard/PageHeader.tsx` | **Orphaned** — superseded by `rx/PageHeading` |
| `dashboard/ActivityFeed.tsx` | **Orphaned** — MasterDashboard hand-rolls its own feed (`MasterDashboard.tsx:421-437`) |
| `dashboard/StatTile.tsx` | Live, but used by **11 back-office pages and *none* of the 3 dashboards**; radius `rounded-2xl` / shadow differ from the dashboard `dxr-tile` (`rounded-[20px] shadow-sm`) |

This split between a dead older layer and the live `rx/*`/`dxr-*` layer is the single biggest source of drift.

### 3. [Major] No shared card primitive → 3+ card vocabularies coexist
- shadcn `<Card>` (`bg-card border-border`, 0.75rem radius) vs bento `.dxr-tile` (20px, 18px padding) vs
  raw `<div>`/`<li>` at `rounded`/`rounded-md`/`rounded-lg`/`rounded-xl`/`rounded-2xl`.
- POSTerminal alone uses **four card radii** (`:1260, :1643, :1712, :2132`).
- ZatcaStatus and WebhookManagement mix shadcn Card + dxr-tile on the same page.

### 4. [Major] No shared table primitive → every list-heavy page hand-rolls a table
- GiftCard, Loyalty, Supplier, Branch, Channel, Product, ReportsAnalytics each build their own `<table>`.
- **Three+ different header treatments** (`bg-card`, `bg-muted/40`, `bg-muted/50`, transparent `border-b`)
  and two row-border opacities.
- Reference `.tbl` (uppercase 10.5px tracked headers, `border-top` rows, `tbody tr:hover`) implemented **nowhere**.
- "A list of records" is rendered three structurally different ways: tables, `<li>` lists
  (Reservations, CatalogModifiers), stacked `<Card>`s (Quotation).

### 5. [Major] Semantic action buttons bypass variants (contrast risk)
- **No `success`/`warning`/`danger` Button variants** exist, so ~15 places hand-roll `bg-success text-white` /
  `bg-warning text-white` / `bg-danger text-white`:
  UserProfile (`:198-208`), LoyaltyProgram (`:252,384`), SupplierManagement (`:590,713`),
  ShiftManagement (`:384`), POSTerminal refund (`:1385`), OrderTicket (`:515`), ZatcaStatus (`:208`),
  ChannelOrders (`:257`).
- `text-white` on the light gold `warning` token is likely a **contrast failure**.

### 6. [Major] Toggles never use the Switch primitive
- `components/ui/switch.tsx` exists and is **used by zero settings pages**.
- UserProfile uses On/Off colored buttons (`:198-208`); StoreSettings uses a `destructive` Button for "closed" (`:208`).
- Reference `.switch`/`.toggle-row` look is unimplemented.
- `.seg`/`dxr-seg` segmented control exists but is used only for the Reports period filter —
  UserProfile language/theme pickers are button grids that should be segmented controls.

### 7. [Major] Hardcoded brand/accent hex + slate palette leakage
- **Cyan accent `#36c5e0`** duplicated in `ClientDashboard.tsx:155`, `rx/Gauge.tsx:51`, SpotChart —
  should be a `--cyan` token (named in `ds.css:18`, never ported to `index.css`).
- **Brand `#1488a6`** retyped as a literal in AgentDashboard (`:224,291`), MasterDashboard `AV_GRADS`
  (`:49-56`), both landing pages. `#1488a6` *is* `brand-500`; `#d7ebf1` *is* `brand-100`.
- **Both landing pages** (`LandingPage.tsx`, `AgentLandingPage.tsx`) are built almost entirely on `slate-*`
  literals + raw hex with **no dark-mode variants** → read as a different product, stay white when the app inverts.

### 8. [Major] RTL regressions from physical margins (Arabic is a primary market)
- OrderTicket, KDS, FloorMap, ChannelOrders use physical `mr-*`/`ml-*` instead of logical `me-*`/`ms-*`.
- Per-page `dir={isRTL}` handling is inconsistent — some set it, others rely on the layout.

### 9. [Minor→Major in aggregate] No shared loading / empty / error states
- Three+ loading treatments (bespoke `animate-pulse` text, spinner ring, nothing); empty states render as
  `<Card>` on some pages and an in-table `<tr>` on others.
- Several pages **swallow errors to `console.error`** and render empty: CatalogModifiers (`:74`),
  Quotation (`:63`), ReceiptTemplateDesigner (`:99`), PackageManagement (`:115`) — while AuditLog/Notifications
  have proper `ErrorState`/`PermissionDenied`/retry.
- No shared `LoadingState`/`EmptyState` to reach for.

---

## Findings by area

### Shell & Core Dashboards
- **[Critical]** Shell mismatch — 256px sidebar (`DashboardLayout.tsx:131`) vs reference 80px `.rail`.
- **[Critical]** Missing command bar — no greeting/⌘K/bell/primary-action in shell (`DashboardLayout.tsx:197-267`).
- **[Major]** ⌘K palette is per-page (MasterDashboard only), not global → hoist `CommandPalette` into shell.
- **[Major]** MasterDashboard inline avatar gradients with hex (`AV_GRADS`, `:49-56`) instead of shared `Avatar`.
- **[Major]** MasterDashboard inline activity feed (`:421-437`) instead of shared `ActivityFeed`.
- **[Major]** AgentDashboard money-flow bars hardcode hex (`:291,294,299-300`) and brand fallback `#1488a6` (`:224`).
- **[Minor]** AgentDashboard degenerate gradient `linear-gradient(135deg, ${c}, ${c})` (`:446`).
- **[Major]** ClientDashboard hardcoded sparkline `#36c5e0` (`:155`) + inline `subStatusCls` duplicating `pill-*` (`:88-92`).
- **[Minor]** ClientDashboard raw status string rendered untranslated (`:213`).
- **[Major]** `StatTile` radius/shadow diverge from `dxr-tile`; **[Critical]** `StatCard` orphaned + raw `emerald/amber/rose`.
- **[Major]** `MrrTrendChart`, `PageHeader`, `ActivityFeed` orphaned.
- **[Minor]** `Avatar` is `rounded-full` but reference + inline leaderboard avatars are `rounded-[10px]` squircles.
- **[Major]** `DashboardLayout.tsx:261` `hover:text-red-500`; **[Minor]** `:216` `text-amber-400` (use tokens).

### Agent-role Management Pages
- **[Critical]** StaffManagement H1 = "Total Staff" (a stat label), not "Staff" (`StaffManagement.tsx:325`).
- **[Major]** Table header split: Product/Discount `bg-muted/40` vs Customer/Staff/Expense `bg-card`.
- **[Major]** ExpenseTracking outlier — raw `<Card>`, raw `<label>`, redundant `bg-muted border-input text-foreground` overrides.
- **[Major]** PackageManagement (`:168-171,185`) & CustomerManagement (`:484-486`) re-implement `pill-*`/brand pills inline; Customer mixes `<Badge>` + `pill-*`.
- **[Minor]** BrandingEditor inline `style={{ padding: 22 }}` (`:149,234`); upload button hand-rolls brand gradient (`:159`).
- **[Minor]** CategoryManagement nested `rounded bg-muted/30` radius mismatch (`:264`); subtitle fallback bug (`:315`).
- **[Minor]** Ad-hoc status toggle buttons (Allow/Deny, Enable/Disable, Activate/Deactivate) across Staff/Discount/Product — no shared variant despite `.seg`.
- **[Minor]** PackageManagement: delete labeled `t('deactivate')` but handler calls `deletePackage` (`:122,206`); silent `catch {}` (`:115,127`).
- **[Minor]** Spacing drift: `space-y-5` (Branding, Package) vs `space-y-6` (rest). RTL `dir` applied on some pages, not others.

### Reports, Audit & Settings Pages
- **[Major]** ReportsAnalytics has **no real chart** — "Sales Overview" is a horizontal `Bar` list (`:962-981`), not the reference cyan-line interactive chart; whole page is shadcn `<Card>`, not bento tiles.
- **[Critical]** UserProfile On/Off toggle buttons hardcode `bg-success text-white` (`:198-208`); `brand-400` avatar tint weak in dark mode (`:121-126`).
- **[Major]** UserProfile language/theme = button grids; should be `dxr-seg` (`:146-178`). `<Badge className="pill-success">` double-wraps (`:223`).
- **[Major]** StoreSettings inline `style={{ padding: 22 }}` (`:98,134,147,183`); "closed" toggle is `Button variant="destructive"` (`:208`) — should be Switch.
- **[Major]** Devices/Printers swallow errors + drop the page header during loading; empty state uses shadcn `<Card>` while rows use `dxr-tile`.
- **[Minor]** AuditLog hand-rolls a `<table>` (`:156`) close to `.tbl` but duplicated; loading is bare pulse vs Reports skeleton.
- **[Minor]** Section-heading icons are bare tinted glyphs (`text-brand-600`/`text-success`/…) instead of `dxr-sw` swatch.

### POS Operational Pages
- **[Major]** Touch targets too small: `h-7 w-7` (28px) steppers POSTerminal (`:1784,:1324`); `size="sm"` KDS Bump (`:473`); FloorMap tiles no min-height (`:385`).
- **[Major]** POSTerminal held-tickets modal is hand-rolled `fixed inset-0 bg-black/60` (`:2128`) while FloorMap/KDS use shadcn `Dialog`.
- **[Major]** POSTerminal four card radii (`:1260,:1643,:1712,:2132`); every CTA/chip hand-rolled instead of `Button`/`chip`/`seg`.
- **[Major]** Two "active" treatments side by side: payment method `bg-brand-50 text-brand-700` (`:1967`) vs category/split `bg-brand text-white` (`:1619,:1937`).
- **[Major]** ShiftManagement & OrderTicket still use shadcn `Card` instead of `dxr-tile`.
- **[Minor]** CustomerDisplay live totals lack `tabular-nums` (`:98,112,116,120`) → jitter; paid hero uses `from-brand-800 to-brand-900` not `.dxr-ink`.
- **[Minor]** Status-color collision: OrderTicket "bumped = success (green)" vs FloorMap "free = success (green)".
- **[Minor]** RTL: OrderTicket/KDS/FloorMap use physical `mr-*`/`ml-*`. OrderTicket/FloorMap use native `<select>` vs shadcn `Select`.

### Restaurant & Commerce Pages
- **[Critical]** BranchManagement over-specifies `bg-card border-border text-foreground` on dialogs + `bg-muted` inputs (others use `bg-background`); raw `<label>` instead of `<Label>`.
- **[Critical]** LoyaltyProgram (`:252,384`) & SupplierManagement (`:590,713`) hardcode `bg-success/bg-danger text-white` action buttons.
- **[Major]** MenuBuilder (shadcn Card) vs functional twin CatalogModifiers (`dxr-tile`) — different card systems.
- **[Major]** Quotation flattens every status to `pill-muted` (`:253`) — draft/sent/converted/expired identical; renders records as stacked `<Card>`s while others use tables.
- **[Major]** No shared table: GiftCard/Loyalty/Supplier/Branch/Channel each hand-roll `<table>` with different headers/row borders.
- **[Major]** Reservations mixes raw token literals + `pill-*` in one status map (`:28-34`); native `<select>` (`:236-238`); `<li>` record lists.
- **[Minor]** Loyalty & Supplier: 3 StatTiles in `lg:grid-cols-4` → dangling empty column. CatalogModifiers/Supplier use `✕`/`×` glyphs instead of lucide icons.
- **[Minor]** Feedback split: `sonner` toasts (Quotation) vs inline `<p role="status">` (GiftCard/Channel/Loyalty). ChannelOrders physical `mr-*`.

### Compliance, Integration, Auth & Landing Pages
- **[Major]** LandingPage & AgentLandingPage pervasive `slate-*` + raw hex (`#1488a6`=brand-500, `#d7ebf1`=brand-100, `#2e7d54`, `#5a4410`, `#e2e8f0`, `#64748b`); no `dark:` variants.
- **[Major]** Index & ForceResetPassword are bare shadcn cards — no logo/gradient/petrol-gold identity, and don't match each other (title sizes, Label vs placeholder).
- **[Minor]** Three "not found" designs: `NotFound.tsx`, AgentLandingPage inline card, others → consolidate.
- **[Minor]** Status semantics drift: ZatcaStatus `failed` → warning tile but danger badge (`:35,44`); WebhookManagement `inactive` → `pill-danger` (should be `pill-muted`).
- **[Minor]** ZatcaOnboarding hand-rolled stepper + ad-hoc step pills (`:127-149`) instead of shared pills; shadcn `<Card>` instead of `dxr-tile`.
- **[Minor]** ReceiptTemplateDesigner inline `style={{ padding: 22 }}` (`:166,252`); no error state (`:99-103`).
- **[Minor]** WebhookManagement three container styles on one page; mixes `pill-*` + shadcn `<Badge>`.

### Housekeeping
- 6 `.fuse_hidden*` junk files in `frontend/src/pages/` (leftover FUSE artifacts, untracked) — safe to delete.

---

## Remediation roadmap (foundation-up)

### Phase 1 — Tokens ✅ DONE 2026-06-17
- [x] Add `--cyan` token + `success-foreground` / `warning-foreground` / `danger-foreground` to `index.css`.
  - `--cyan` lives in `index.css`; the contrast-safe foregrounds live on the `success`/
    `warning`/`danger` colours in `tailwind.config.ts` (gold `warning` → dark ink).
- [x] Purge hex literals: `#36c5e0`, `#1488a6`, `#0e7693`, `#d6a33a`/`#cd9a40`, `#3a2c10`, `#d7ebf1` → tokens.

### Phase 2 — Shared primitives ✅ DONE 2026-06-17
- [x] Delete orphaned components: `StatCard`, `MrrTrendChart`, `PageHeader`, `ActivityFeed`.
- [x] Settle one card (`dxr-tile`), one `DataTable` (`.tbl` spec → `rx/DataTable`), one `PageHeader` (= `rx/PageHeading`).
- [x] Add `Button` semantic variants: `success` / `warning` / `danger` (+ outline-danger).
- [x] Adopt existing `Switch` (`ui/switch.tsx`) and `dxr-seg` for all toggle/segmented settings.
- [x] Add shared `LoadingState` + `EmptyState`; align `StatTile` radius/shadow to `dxr-tile`.

### Phase 3 — Shell (highest visibility) ✅ DONE 2026-06-17
- [x] Migrate `DashboardLayout` to 80px icon rail + command bar (greeting, ⌘K, bell, primary action).
- [x] Hoist `CommandPalette` into the shell so ⌘K is global on all three dashboards.
  - New `PageChromeContext` (`usePageChrome`) lets each page feed the shell its subtitle / primary
    action / ⌘K quick-actions; Master/Agent/Client dashboards no longer hand-roll their own top chrome.

### Phase 4 — Page sweep (mostly mechanical once Phase 2 lands) ✅ DONE 2026-06-17
- [x] Move pages onto shared Card / DataTable / Button variants / Switch / pills.
  - [x] Button `success`/`warning`/`danger`/`outline-danger` variants adopted across AgentDashboard,
        LoyaltyProgram, SupplierManagement, PackageManagement, CustomerManagement, POSTerminal,
        OrderTicket, KDS, ZatcaStatus, ChannelOrders, ShiftManagement (no more `bg-* text-white`).
  - [x] UserProfile notification On/Off buttons → `Switch`.
  - [x] Hand-rolled tables now use the shared **`DataTable`** primitive (`rx/DataTable`, the `.dxr-tbl`
        spec): GiftCard, Supplier (×2), Loyalty (×2), Branch (×2), Channel, Product (×3), and the
        Webhook delivery-logs table (the last non-`dxr-tbl` outlier). Cell-only styling moved into
        column `cell` renderers (a column `className` lands on both `<th>` and `<td>`); actions columns
        use `align: 'end'`; in-table empty `<tr>`s moved to the `empty` prop. GiftCard/Webhook empty
        `<Card>` → shared `EmptyState`.
  - [x] Card→`dxr-tile` vocabulary unification — MenuBuilder (6 Cards), ZatcaOnboarding (2 Cards),
        WebhookManagement (empty-state Card → `EmptyState`); unused `@/components/ui/card` imports
        removed. (ReportsAnalytics' Card→tile + real-chart rework is tracked separately under the
        Reports findings, not Phase 4.) ZatcaOnboarding's custom step-rail left as-is — its per-state
        borders aren't expressible with the shared `pill-*` set.
- [x] Fix RTL `mr-*`→`me-*`, native `<select>`→shadcn `Select`, physical→logical props.
  - [x] Physical→logical margins in OrderTicket / KDS / FloorMap / ChannelOrders.
  - [x] native `<select>` → shadcn `Select` — OrderTicket (6), FloorMap (3), Reservations (2). Number
        bindings string-coerced (`String(x)` in / `Number(v)` out); empty/"all" `<option value="">`s
        replaced with a `"none"` sentinel (Radix forbids empty-string item values); classes/dir/aria
        carried onto `SelectTrigger`. ⚠ behaviour-identical & green on build+lint, but worth a quick
        visual pass on the dropdowns.
- [x] Fix StaffManagement title bug; Quotation status→pill map; POS touch-target sizes; inline-padding magic numbers.
  - StaffManagement H1 (`stf_total_staff` → `staff`); Quotation status→distinct pills;
        POS steppers `h-7`→`h-9`, KDS Bump full-size, FloorMap tile `min-h`; all `style={{ padding }}`
        magic numbers removed (revert to `.dxr-tile` default `p-[18px]`, or `p-0` for flush tables).
- [x] Replace error-swallowing `catch` blocks with `ErrorState` (CatalogModifiers, QuotationManagement,
      ReceiptTemplateDesigner; PackageManagement actions now log instead of silent-fail).

### Phase 5 — Public pages ✅ DONE 2026-06-17
- [x] Landing pages **gated as intentionally light** (the sanctioned alternative).
  - Both `LandingPage` & `AgentLandingPage` paint on *fixed* palettes only (`slate-*`
    neutrals + `brand`/`gold`/`success`, plus the agent's own `primary_color` via inline
    style) — none are theme tokens, so they never half-invert when the app is dark and a
    logged-out visitor has no toggle. Re-tokening to app tokens would force them to invert
    and break the brochure, so we documented the light decision in a header comment on each
    instead. Stray gold-ink hex `#5a4410` → new `gold-900` token; the green "Another Agent"
    mock greens left as intentional literals (a deliberately *different* brand) with a note.
- [x] Auth screens branded + unified via shared **`AuthLayout`** (`components/auth/`):
    gradient logo lockup, soft petrol wash, one token-based card. `Index` (login) and
    `ForceResetPassword` both adopt it; ForceReset keeps its in-form CL-02 language step so
    it passes `showLanguageSwitcher={false}`. Both stay token-based → still theme correctly.
- [x] "Not found" consolidated into shared **`NotFoundState`** (`components/states/`):
    route-level `NotFound` is now a thin wrapper; `AgentLandingPage`'s "distributor not
    found" branch reuses it (custom icon/title/action), dropping its bespoke `<Card>`.

### Phase 6 — Cleanup ✅ DONE 2026-06-17
- [x] Delete `.fuse_hidden*` junk files.
- [x] Document the status→token color map (one source of truth for success/warning/danger/muted semantics).
  - New `docs/STATUS_COLOR_MAP.md`: meaning of each colour (success/warning/danger/
    sky/muted/violet + gold-as-emphasis), the canonical per-domain status maps already
    in code, and rules for adding a new status. Resolves the two open drift findings as
    *intentional*: (a) operational `inactive`→`pill-danger` (Webhook included) vs
    catalogue `inactive`→`pill-muted`; (b) `StatTile` has no `danger` tone by design, so
    an error status is a `warning` tile + `pill-danger` badge (ZatcaStatus `failed`).
    Pointer comment added in `index.css` above the `.pill-*` block.

**Recommended start:** Phase 1 + Phase 2 (tokens + primitives) — everything else builds on them.
