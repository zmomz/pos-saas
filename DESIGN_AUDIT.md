# Design Consistency Audit — All Dashboards

> Audit of all ~38 frontend pages (Master / Agent / Client+POS dashboards) against the
> newly-redesigned "gold standard" design system (`dxr-*` bento tiles, `rx/` component kit,
> `pill-*` badges, semantic tokens, `formatMoney`, `PageHeading`). Date: 2026-06-17.

## TL;DR

The redesign landed beautifully on **4–5 flagship screens** but stopped there. Of ~38 pages,
only **7 are on the new design system**; the other **~31 are still pre-redesign**. The result is
a split-brain product: Master/Agent dashboards look like a 2026 SaaS, but the moment you open
Products, Reports, or the **POS terminal itself**, you're back in the old indigo-era app with raw
color literals and `<Card>` boxes.

> ⚠️ **Correction to the original premise:** "master, agent and **POS**" were assumed redesigned —
> but **POSTerminal was *not* migrated to the new system.** It still uses legacy `Card`/`Badge`
> primitives, 27 raw color literals, a custom `SAR()` money formatter, and hardcoded English
> strings. It's the single largest off-brand surface in the app, and it's the screen cashiers
> stare at all day. (POS was *re-skinned to light/petrol* in the earlier pass, but never rebuilt
> on the new `dxr-tile`/`rx` bento system.)

## Where each page stands

| Tier | Pages | State |
|------|-------|-------|
| ✅ **On-system (reference / nits only)** | MasterDashboard, AgentDashboard, PackageManagement, BrandingEditor, AuditLog, Notifications, ClientDashboard\* | Use these as the templates |
| 🟡 **Close, light touch-up** | Reservations | Already uses tokens + shared states |
| 🔴 **Pre-redesign — full conversion needed** | **POSTerminal**, ReportsAnalytics, ProductManagement, QuotationManagement, CustomerManagement, StaffManagement, SupplierManagement, LoyaltyProgram, GiftCardManagement, DiscountManagement, CategoryManagement, CatalogModifiers, MenuBuilder, FloorMap, OrderTicket, KDS, ChannelOrders, StoreSettings, PrinterSettings, DevicesSettings, ReceiptTemplateDesigner, WebhookManagement, ExpenseTracking, ShiftManagement, ZatcaStatus, ZatcaOnboarding, BranchManagement, UserProfile | ~28 pages |
| 🌐 **Public/standalone (own palette)** | Index, ForceResetPassword, NotFound, CustomerDisplay, LandingPage, AgentLandingPage | Off-token but partly intentional |

\*ClientDashboard is structurally on the new system but has a few drift points (hand-rolled status
badge, raw-hex sparkline instead of `SpotChart`).

---

## The 8 systemic problems (ranked by visual impact × frequency)

These recur across nearly every 🔴 page — fixing them as **sweeps** will do more than any
single-page rework.

### 1. Forbidden color literals everywhere — *the #1 off-brand signal*

Raw Tailwind palette colors instead of semantic tokens, on virtually every legacy page. The design
system defines `success / danger / warning / violet / gold / sky` + `pill-*` + `dxr-sw-*`, but
pages use:

- `green-*` / `emerald-*` → should be `success`
- `red-*` → `danger` / `destructive`
- `amber-*` / `yellow-*` → `warning` / `gold`
- `purple-*` → `violet`
- **off-palette colors that don't even exist in the system:** `orange-*` (Staff, ChannelOrders),
  `pink-*` (GiftCard — invented brand color), `gray-*`/`slate-*` (Reports, landing)
- `text-white` / `text-black` on non-colored surfaces

Worst offenders: status-badge maps built entirely from literals — `STATE_BADGE` (FloorMap:34),
`STATUS_BADGE` (ChannelOrders:23, ZatcaStatus:29), `FIRE_BADGE` (OrderTicket:64), `getStatusBadge`
(SupplierManagement:374), `segmentClass` (CustomerManagement:302). These break dark mode and
white-label theming.

### 2. POSTerminal is the biggest single liability

Beyond the color literals: legacy `Card`/`Badge` receipt, custom `SAR()` helper
(POSTerminal:676) that ignores `language` (no Arabic-Indic digits), `product.price.toFixed(2)` +
literal "SAR" on tiles, bespoke `h2` header instead of any standard, and hardcoded English error
strings (507, 539, 571, 734). This should be **priority one**.

### 3. Currency is formatted ~4 different ways

The system standard is `formatMoney(value, language)`. Instead found:

- hardcoded `$` (ProductManagement:952)
- `SAR ${n.toFixed(2)}` (ExpenseTracking, ShiftManagement, DiscountManagement, SupplierManagement, GiftCardManagement)
- bare `.toFixed(2)` with no symbol (OrderTicket — ~13 places, MenuBuilder)
- `{tr('sar')} {n.toLocaleString(...)}` in **~40 places** in ReportsAnalytics
- custom `SAR()` (POSTerminal)

None of these localize digits for Arabic. This is both a polish *and* a correctness issue.

### 4. No standard page header

Only on-system pages use `PageHeading` (`h1 text-[21px] font-extrabold` + `text-[13px]` subtitle +
right-aligned actions). The rest use `h2 text-xl font-bold`, `text-2xl`, in-card `text-lg` titles,
or **no header at all** (Customer, Staff, Discount, Shift jump straight into stat cards). Four pages
(POSTerminal, ProductManagement, QuotationManagement, ReportsAnalytics) even render their **own
`min-h-screen` shell + back button + language switcher**, double-padding inside DashboardLayout.

### 5. `<Card>` stat tiles instead of `dxr-tile` / `KpiChip`

Every legacy KPI row uses plain shadcn `<Card>` + `text-2xl font-bold` with bare colored icons — no
`dxr-sw` icon swatch, no `dxr-delta` chip, no `tabular-nums`. Affects ProductManagement,
DiscountManagement, CustomerManagement, StaffManagement, SupplierManagement, LoyaltyProgram,
ExpenseTracking, ReportsAnalytics, ZatcaStatus, WebhookManagement, BranchManagement, UserProfile.
This is why metrics look visually "lighter" than the dashboards.

### 6. Primary buttons bypass the Button variant

`bg-brand-600 hover:bg-brand-700 text-white` hardcoded on virtually every action button — loses
`shadow-brand` and the `h-11 rounded-[10px]` sizing. The default `<Button>` variant already *is*
brand. This appears on essentially every 🔴 page.

### 7. Hardcoded English / inconsistent i18n

Three i18n styles coexist: `tt(key, fallback)` (Master), `t('key') || 'fallback'` (Agent/Client),
and bare `t()`. Worse, several pages have **dozens of hardcoded English JSX strings** with no
translation at all: ProductManagement (~30), CategoryManagement (~20), LoyaltyProgram (heavy),
ExpenseTracking, BranchManagement, UserProfile, Notifications. Arabic users see English.

### 8. Smaller-but-pervasive drift

- **Native `<select>`/`<input type=checkbox>`** hand-styled instead of shadcn `Select`/`Checkbox`
  (BranchManagement, SupplierManagement, PrinterSettings, DevicesSettings, ReceiptTemplateDesigner,
  MenuBuilder, CatalogModifiers, ZatcaOnboarding)
- **Tab switchers as two `<Button>`s** instead of the `dxr-seg` segmented control
  (SupplierManagement, LoyaltyProgram, WebhookManagement, ReportsAnalytics, KDS, FloorMap)
- **Triplicated inline offline banner** (FloorMap:249, OrderTicket:453, KDS:318) instead of the
  shared `OfflineBanner` component
- **Physical RTL props** (`mr-1`, `pl-8`, `ml-2`) that break Arabic, scattered across
  CategoryManagement, MenuBuilder, SupplierManagement, LoyaltyProgram, BranchManagement,
  ZatcaStatus/Onboarding, UserProfile, both landing pages
- **Missing `animate-fade-up`** on most legacy page roots
- **Loading states** as `'...'` string (ReportsAnalytics) or centered text instead of skeletons

---

## Recommended fix order

1. **POSTerminal** — highest-traffic, most off-brand. Rebuild on `dxr-tile`/`Button`/`pill-*` +
   `formatMoney`. (Big job, biggest payoff.)
2. **Two global sweeps** (cheap, huge consistency win across all 28 pages):
   - Color-literal → semantic-token / `pill-*` codemod
   - Currency → `formatMoney(value, language)` codemod
3. **ReportsAnalytics** — highest-effort single page (~40 inline currency sites, bespoke
   charts/badges, own shell). Schedule on its own.
4. **Adopt `PageHeading` + `dxr-tile` StatTiles** page-by-page, starting with the most-visited
   (Products, Customers, Reports already covered, Staff).
5. **i18n pass** on the worst offenders (Product, Category, Loyalty, Branch, UserProfile).
6. **Polish sweep**: shared `OfflineBanner`, `dxr-seg` tabs, logical RTL props, `animate-fade-up`,
   native-control → shadcn.

---

## Appendix — per-page findings

Severity: **High** = looks broken/off-brand/inconsistent at a glance · **Medium** = noticeable
polish gap · **Low** = nit.

### Flagship dashboards

#### MasterDashboard (✅ reference)
- [Low] :278 / :454 — hardcoded `+11.4%` delta and `99.98%` / "Uptime 30d" are fabricated literals (acceptable on the reference, but copied elsewhere).
- [Low] :212–219 — `mrrLabels`/`mrrTicks` month names hardcoded English, not via `t()`.

#### AgentDashboard (✅ minor)
- [Medium] :291–300 — revenue split bar uses raw inline hex gradients (`#1488a6`,`#0e7693`,`#d6a33a`…) instead of brand/gold tokens.
- [Medium] :283 — error text `text-[hsl(6_70%_80%)]` is a raw HSL literal → semantic danger token.
- [Medium] whole file — uses `t('key') || 'fallback'` instead of Master's `tt(key, fallback)` helper.
- [Low] :224/446/458 — `linear-gradient(135deg, ${brandColor}, ${brandColor})` is a same-color no-op gradient → solid background.
- [Low] :334 — `{remainingSlots} of {slotCapacity}` hardcodes English "of".

#### ClientDashboard (✅ structurally on-system, drift points)
- [Medium] :154–155 — sparkline `<polyline stroke="#36c5e0">` raw hex instead of `SpotChart`/token.
- [Medium] :212–214 — subscription badge hand-rolled instead of `pill-*`.
- [Medium] :88–92/213 — `subscription_status` rendered raw (`past_due`, `dunning`) with no `t()`.
- [Low] :133 — "Pay now" uses `text-[#3a2c10]` raw hex → define `gold-foreground` token.

#### POSTerminal (🔴 NOT redesigned — top priority)
- [High] — 27 forbidden color literals (`text-orange-400/600`, `text-green-400`, `bg-green-900/50`, `text-red-400`, `border-red-600`, `text-amber-300`, `text-emerald-300`, `bg-gray-100`) across receipt/refund/void/barcode/cart (lines incl. 1063,1084,1104,1114,1173,1223,1370,1384,1406,1462,1553,1722,1759,1829,1854,2150).
- [High] :676 — custom `SAR()` helper ignores `language` (no Arabic-Indic digits) → `formatMoney`.
- [High] :1665 — product tile uses `product.price?.toFixed(2)` + literal "SAR".
- [High] :1060/1114/1179/1229/1847 — `Card`/`Badge` primitives + `bg-brand-600` button styling instead of `dxr-tile`/`Button`/`pill-*`.
- [Medium] :507,539,571,734 — hardcoded English strings in error messages.
- [Medium] — page root lacks `animate-fade-up`/`PageHeading`; bespoke `h2` header.
- [Medium] :1543,1717,1802 — `bg-brand-900/30`, `text-brand-300/400` brand-shade drift.

### Catalog / Products

#### PackageManagement (✅ back-office reference)
- [Low] :185 — feature pills ad-hoc instead of shared `pill-*`.
- [Low] :168 — status badge hand-rolled instead of `pill-success`/`pill-muted`.

#### ProductManagement (🔴 worst structural offender)
- [High] :677–704 — legacy `min-h-screen` shell + custom header/back/lang instead of `PageHeading` inside DashboardLayout.
- [High] :952 — `${product.price.toFixed(2)}` (hardcoded `$` + bare toFixed) → `formatMoney`.
- [High] :1129 — variant price bare `.toFixed(2)`.
- [High] :718,724,772,777,882,948,955,970,1018,1027,1080,1145 — `orange-/green-/red-*` literals → success/danger/warning + `pill-*`.
- [High] :709–727 — stat cards use `<Card>` + `text-2xl font-bold`, no `dxr-tile`/`dxr-sw`/`tabular-nums`.
- [High] ~30 strings — hardcoded English JSX ("Name *", "Barcode", "Total Products", "Search products…", table headers, etc.).
- [Medium] :659,858,1225 — primary buttons `bg-brand-600…` instead of default Button + `shadow-brand`.

#### CategoryManagement (🔴)
- [High] :314–342 — header in a `<Card>` `text-lg font-bold`, not `PageHeading`; missing `animate-fade-up`.
- [High] :229,254,287,348,388 — `red-*` delete buttons → `danger` tokens.
- [High] ~20 hardcoded English strings.
- [Medium] :225 — tree node `rounded-lg` not `dxr-tile`.
- [Medium] :234,261,270 — physical `mr-1`/`pl-8` → `me-1`/`ps-8` (RTL).

#### CatalogModifiers (🔴)
- [High] :129–134 — `text-xl font-semibold` header not `PageHeading`; missing `animate-fade-up`.
- [High] :191 — chip `bg-brand-petrol/30 text-white` + bare "✕" instead of `pill-*` + icon.
- [High] :278 — combo bundle price raw `{c.bundle_price}` (no formatting) → `formatMoney`.
- [Medium] :126–127 — raw `<select>` instead of shadcn `Select`.
- [Medium] :137,176,225 — plain `<Card>` not `dxr-tile`.

#### MenuBuilder (🔴)
- [High] :307–311 — `text-xl font-bold` header not `PageHeading`; missing `animate-fade-up`.
- [High] :301,345,287,425,431 — `amber-*`/`red-*`/`brand-300` literals → warning/danger/`pill-*`.
- [High] :431,435,565,803 — money with bare `.toFixed(2)` / unformatted `(p.price)`.
- [Medium] :497–515,598–616 — raw `<select>` instead of `Select`.
- [Medium] :289,313,520,632 — manual brand buttons.
- [Low] :433 — physical `ml-2` → `ms-2`.

#### DiscountManagement (🔴)
- [High] :355–388 — no `PageHeading`; `<Card>` stat tiles; missing `animate-fade-up`.
- [High] :370,373,379,436,445,466,497,515,557 — `green-/purple-/amber-/red-/orange-*` literals → success/violet/warning/danger + `pill-*`.
- [High] :446,449 — `SAR ${discount.value}` / `SAR ${min_purchase}` raw → `formatMoney`.
- [Medium] :413 — inline status badges instead of `pill-*`.

### People / CRM

#### CustomerManagement (🔴)
- [High] :415–455 — no `PageHeading`; opens into stat cards; missing `animate-fade-up`.
- [High] :419–453 — `<Card>` stat tiles, bare colored glyphs, no `tabular-nums`.
- [High] :302–309 — `segmentClass` uses `amber-/red-/green-*` literals → `pill-*`.
- [High] ~25 hardcoded English strings (form labels, table headers, "No customers found", stat labels).
- [High] :749,759 — lifetime value / basket via `.toFixed(2)` + "SAR"; `language` not even destructured → `formatMoney`.
- [High] :519,673,692,707 — `red-/amber-*` error/delete/erase buttons → destructive/warning variants.

#### StaffManagement (🔴 — cleanest on i18n, good model)
- [High] :321–352 — no header; `<Card>` stat tiles, no `dxr-sw`/`tabular-nums`; missing `animate-fade-up`.
- [High] :339,407,424,493,538 — `green-/red-/orange-*` literals (orange not in palette) → success/danger/warning + `pill-*`.
- [Medium] :513 — `text-orange-400` "no login" alert → `text-warning`.
- [Low] :401 — role badge `bg-muted text-foreground/90` → `pill-muted`.

#### SupplierManagement (🔴)
- [High] :441–481 — no header; `<Card>` stat tiles.
- [High] :374–384 — `getStatusBadge` entirely `gray-/amber-/green-/red-*` literals → `pill-*`.
- [High] :589,657 — `SAR {…toFixed(2)}`; `formatMoney` not imported.
- [Medium] :484–491 — tab switcher as Buttons → `dxr-seg`.
- [Medium] :595 — physical `mr-1` → `me-1`.
- [Medium] :629–684 — native `<select>` → shadcn `Select`.

#### LoyaltyProgram (🔴 — heavy hardcoded English)
- [High] :166–201 — no header; `<Card>` stat tiles; missing `animate-fade-up`.
- [High] :181,193,259,319,363,391 — `yellow-/green-/red-*` literals (yellow → gold) + `pill-*`.
- [High] ~25 hardcoded English strings.
- [Medium] :279–286 — tab switcher as Buttons → `dxr-seg`.
- [Medium] :393,399 — physical `mr-1` → `me-1`.

#### GiftCardManagement (🔴)
- [High] :19–24,171,267,296,320 — `green-/amber-/red-*` + **invented `pink-*`** brand color → `pill-*` + `brand`.
- [High] :221,296 — pink buttons use `text-foreground` on colored fill → `bg-primary text-primary-foreground`.
- [High] :263,265 — balance `.toFixed(2)` + `{currency}` → `formatMoney`.
- [Medium] :168–183 — `text-xl font-bold` header → `PageHeading`.

#### QuotationManagement (🔴 — worst structural offender)
- [High] :154 — own `min-h-screen` shell + back button, bypasses DashboardLayout.
- [High] :159 — `text-2xl font-bold` header → `PageHeading`.
- [High] :240,269,272,282 — `green-/red-*` save/convert/delete buttons → tokens.
- [Medium] :268 — status badge raw `q.status`, untranslated, not `pill-*`.

### Restaurant ops

#### Reservations (🟡 — closest to gold standard)
- [Medium] :197 — `text-2xl font-semibold` header → `PageHeading` / `text-[21px]`.
- [Medium] :266,350 — `bg-brand-600` buttons → default Button + `shadow-brand`.
- [Low] :29–31 — `seated`/`cancelled`/`no_show` all collapse to identical `bg-muted` badge.
- [Low] :189 — root lacks `animate-fade-up`.

#### FloorMap (🔴)
- [High] :29–31 / :34–38 — `STATE_STYLES` / `STATE_BADGE` use `green-/amber-*` literals → `pill-*` / semantic.
- [High] :234,417 — `text-red-400` / `text-green-400` → `destructive`/`success`.
- [Medium] :249,453 — inline offline-banner literals → shared `OfflineBanner`.
- [Medium] :258 — `h2 text-xl font-bold` header not standard.
- [Medium] :236,294,304,356,473,522 — ad-hoc `bg-brand-600` buttons.

#### OrderTicket (🔴)
- [High] :64–68 — `FIRE_BADGE` `amber-/green-*` literals → `pill-warning`/`pill-success`.
- [High] :536,680,1103 — fire/settle buttons `bg-amber-600`/`bg-green-600` → semantic.
- [High] :635,650,779 — settled/error/required-modifier banners `green-/red-*` → tokens/`pill-*`.
- [High] :570,599,618,1039,1097,1133 — currency via bare `.toFixed(2)` (~13 sites) → `formatMoney`.
- [Medium] :453 — duplicated offline banner → `OfflineBanner`.
- [Medium] :468 — `h2 text-xl font-bold` header.

#### KDS (🔴)
- [High] :336–340 — live/reconnecting badge `green-/amber-*` → `pill-*`.
- [High] :472,481 — late-ticket `border-red-600/50` + `text-red-400` timer → destructive.
- [High] :495 — modifier `text-amber-300` → warning/gold.
- [High] :303,510 — error icon / bump button `red-/green-*` → semantic.
- [Medium] :318 — duplicated offline banner → `OfflineBanner`.
- [Medium] :327 — `h2 text-xl font-bold` header.
- [Low] :396–426 — board/station tabs hand-rolled → `dxr-seg`.

#### ChannelOrders (🔴)
- [High] :23–27 — `STATUS_BADGE` `green-/amber-/emerald-*` literals (emerald not in palette) → `pill-*`.
- [High] :176,225 — connected badges `bg-green-500/20` → `pill-success`.
- [High] :222,254 — aggregator section `orange-*` (not in palette) → warning/gold/brand.
- [Medium] :298 — total `${o.total_amount} ${o.currency}` no `formatMoney`/`tabular-nums`.
- [Medium] :154 — `h2 text-xl font-bold` header.

### Settings / Devices / Config

#### BrandingEditor (✅ forms reference)
- [Medium] :62,65,117,120 — hardcoded English toast strings → `t()`/`tt()`.
- [Medium] :227 — save Button lacks `h-11 rounded-[10px]`.
- [Low] :149,234 — `dxr-tile` overridden with inline `style={{ padding: 22 }}` → use `p-[18px]`.

#### StoreSettings (🔴)
- [High] :86–87 — `text-2xl font-bold` header → `PageHeading`.
- [High] :135,153,194,223 — `green-/purple-/yellow-/red-*` literals → tokens.
- [High] :235 — `bg-brand-600` save button → default Button + `shadow-brand`.
- [Medium] :100–178 — raw `<label>` + redundant input classes instead of ui `<Label>`/bare `<Input>`.
- [Medium] :91–191 — `<Card>` instead of `dxr-tile`.

#### PrinterSettings (🔴)
- [High] :120–128 — header buried in Card `text-lg font-bold`; subtitle is a stray count.
- [High] :154–174 — raw `<select>` → shadcn `Select`.
- [High] :243 — `text-amber-400` default badge → `pill-gold`.
- [High] :264 — `red-*` delete button → destructive variant.
- [Medium] :198–204 — raw `<input type=checkbox>` → ui Checkbox/Switch.
- [Medium] :135,211 — `'+ '` text glyph instead of `<Plus>` icon.

#### DevicesSettings (🔴)
- [High] :89–96 — buried-in-Card header → `PageHeading`.
- [High] :123–130 — raw `<select>` → `Select`.
- [Medium] :193 — `text-emerald-400` status text → `pill-success`.
- [Medium] :178–180 — ad-hoc list rows → `dxr-tile`.

#### ReceiptTemplateDesigner (🔴)
- [High] :147–155 — header buried in Card → `PageHeading`.
- [High] :201–227 — two raw `<select>` → `Select`.
- [High] :264,267 — `emerald-/red-*` status text → tokens / toast.
- [Medium] :231–249 — raw checkboxes → ui Checkbox.
- [Low] :283 — preview `bg-white text-black` is **intentional** (thermal-paper simulation) — not a fix.

#### WebhookManagement (🔴)
- [High] :329,341,404,418,472 — `green-/purple-/red-*` literals → semantic + `pill-*`.
- [High] :317–351 — `<Card>` stat cards → `dxr-tile`/StatTile.
- [Medium] :354–360 — tab switcher as Buttons → `dxr-seg`.

### Finance / Compliance / Ops

#### ReportsAnalytics (🔴 — highest-effort single page, ~1968 lines)
- [High] :868–877 — `rankBadge` uses `yellow-500 text-black` / `gray-300` / `amber-700 text-white` + emoji medals → `pill-*`/`dxr-sw`.
- [High] :1182,1780 — journal & refund/void badges `emerald-/red-/amber-*` literals → `pill-*`.
- [High] :883–923 — own `min-h-screen p-4 md:p-8` shell + own `dir`; double-pads inside DashboardLayout; no `animate-fade-up`.
- [High] :886–923 — `text-2xl font-bold` header + back-arrow glyph + inline lang Select → `PageHeading`.
- [High] pervasive — currency hand-rolled as `{tr('sar')} {n.toLocaleString(...)}` in **~40 places** → `formatMoney`.
- [High] :1303,1339,1484,1865 — `text-emerald-400` profit/margin → `text-success`.
- [High] 9× — `text-red-400` error text → `ErrorState`/`text-danger`.
- [High] :944–987 — KPI cards plain `<Card>` `text-2xl`, no `tabular-nums`/delta/swatch → `dxr-tile`.
- [Medium] :926–941 — period selector as Buttons → `dxr-seg`.
- [Medium] :1014–1037 — manual `bg-brand-600` bar chart → rx `Bar`/`SpotChart`.
- [Medium] — loading state is literal `'...'` (~16 sites) → spinner/skeleton.

#### ExpenseTracking (🔴)
- [High] :239–260,343,358,401 — `red-/green-*` literals → tokens / destructive Button.
- [High] :242,251,284,343 — `SAR {n.toFixed(2)}` → `formatMoney`; no `tabular-nums`.
- [High] ~25 hardcoded English strings.
- [High] :233–266 — `<Card>` stat tiles, no `dxr-sw`/delta.
- [Medium] :234 — no `animate-fade-up`; no error state (failed load shows empty silently).

#### ShiftManagement (🔴)
- [High] :311,351,430,522 — `green-/amber-/red-*` status & cash-difference literals → `pill-*`/tokens.
- [High] :317,375,530 — open/close buttons `bg-red-600`/`bg-green-600` → destructive/success variants.
- [High] :303,361,426,493 — `SAR {n.toFixed(2)}` (current shift, history, close math, `−SAR` movements) → `formatMoney`.
- [Medium] :279–288 — no page header.
- [Low] :251 — `formatDuration` returns hardcoded `${h}h ${m}m` (untranslated units).

#### ZatcaStatus (🔴)
- [High] :29–34,172,235,262 — `STATUS_BADGE` entirely `green-/emerald-/amber-/red-/brand-*` literals → `pill-*`.
- [High] :187–204 — stuck-doc alert + reconcile button `amber-*` literals → warning tokens.
- [Medium] :155–159 — `h2 text-xl font-bold` header → `PageHeading`.
- [Medium] :225–241 — count cards plain `<Card>`, no `tabular-nums`/swatch → `dxr-tile`.
- [Low] :166 — physical `mr-2` → `me-2`.

#### ZatcaOnboarding (🔴)
- [High] :99,137–140,163,203 — `emerald-*` + step-rail `brand-/emerald-*` literals + `bg-brand-600` buttons → tokens / default Button.
- [Medium] :151 — `text-amber-300` notice → `text-warning`.
- [Medium] :190–198 — OTP raw `<input>` → shadcn `Input`.
- [Low] :177,205,221 — physical `mr-2` → `me-2`.

#### BranchManagement (🔴)
- [High] :403,433,482,606,676 — branch/inventory/transfer status literals (`green-/red-/yellow-/brand-*`) → `pill-*`.
- [High] ~25 hardcoded English strings.
- [High] :334,372,551,688 — `bg-brand-600` buttons → default Button.
- [Medium] :352–358 — `h2 text-xl font-bold` header → `PageHeading`.
- [Medium] :504–661 — native `<select>` → shadcn `Select`.
- [Low] :362–439 — many physical `mr-1`/`mr-2` → `me-*`.

### Shared / auth / public

#### AuditLog (✅ nits)
- [Low] :135,157 — inline `style={{ padding: 14 }}` overrides `dxr-tile` padding → Tailwind utility.
- [Low] :182 — hand-rolled action pill → shared `pill-*`.

#### Notifications (✅ on-system but i18n gap)
- [High] :79–88 — title/"Mark all as read"/`${unreadCount} unread`/"All caught up" hardcoded English (per-language ternaries / no i18n) → `t()`/`tt()`.
- [Low] :127 — inline `style={{ padding: 16 }}` → `p-4`.

#### UserProfile (🔴 — major shared-page outlier)
- [High] :108–280 — entire page raw `<Card>`, no `PageHeading`, no title/subtitle, no `animate-fade-up` → migrate to `dxr-tile` + `PageHeading`.
- [High] :137,165,198,233 — card-title icons `green-/purple-/yellow-/red-*` → tokens.
- [High] :218,243,268 — toggle/session-badge/password-error `green-/red-*` → success/danger + `pill-success`.
- [High] :117,148,274 — `bg-brand-600` buttons → default Button.
- [Medium] — pervasive hardcoded English (Profile, Display Name, Light/Dark, alert labels, On/Off, Security & Sessions…).
- [Medium] :285 — `'✓ Saved!'` glyph + English → `t()` + `<Check>` icon.

#### CustomerDisplay (🌐 public)
- [High] :59–63 — paid screen `from-green-900`/`text-green-400` literals → brand-gradient/`success`.
- [High] :89,119 — `text-brand-400` qty / `text-green-400` total → semantic.
- [Medium] :97–119 — currency `.toFixed(2)` + `t('cd_currency')` → `formatMoney`.

#### Index — login (🌐 public)
- [High] :125 — `text-red-400` error → `text-destructive`.
- [High] :130 — `bg-brand-600` submit button → default Button.
- [Medium] :68–88 — login card has no brand mark/logo accent (off-brand vs landing).

#### ForceResetPassword (🌐 public)
- [High] :161 — `text-red-400` error → `text-destructive`.
- [High] :173 — `bg-brand-600` save button → default Button.

#### NotFound (🌐 public)
- [High] :13 — `text-amber-400` → `text-warning`/`text-gold-600`.
- [High] :22 — bespoke button link → `<Button asChild>`.
- [Medium] :16–25 — hardcoded English + awkward `{t('back')} Home` concatenation.

#### LandingPage (🌐 public marketing)
- [High] :299–323 + many — built almost entirely on `slate-*` + `bg-white`; bypasses tokens, no dark-mode variant → map slate ramp to `muted`/`border`/`foreground`.
- [Medium] :260–266 — `RevenueChart` hardcodes `#1488a6`/`#fff` → drive from `hsl(var(--primary))` (won't follow white-label).
- [Medium] :396,437,505 — raw hex `#5a4410` (gold-foreground), `#2e7d54`/`#3f9d6a` greens not in palette → tokens.

#### AgentLandingPage (🌐 public white-label)
- [High] :291–313 — loading/not-found states use `bg-white`/`slate-*` literals; spinner ignores agent `primary_color`.
- [High] :354 + throughout — entire page on `bg-white text-slate-900` + `slate-*`, no dark-mode variant → map to tokens.
- [Medium] :317,427 — static green fallback `#006C35` when no `primary_color` set → fall back to brand token.
