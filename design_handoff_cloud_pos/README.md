# Handoff: Cloud POS — Multi-Tenant White-Label POS Platform (5 screens)

## Overview
Cloud POS is a multi-tenant, ZATCA-compliant Point-of-Sale platform for the Saudi market, serving retail and restaurant businesses. It is **white-label**: resellers ("agents") brand and sell it to merchants ("clients"), who run day-to-day sales. This bundle contains five fully-designed screens spanning four personas (Master / Agent / Client / Staff), plus a shared design system.

The five screens:
1. **Master Landing** (`/`) — partner/reseller recruitment marketing page
2. **Agent Landing** (`/d/:agentId`) — themeable merchant-facing marketing page
3. **Master Dashboard** (`/master`) — platform owner command center
4. **Agent Dashboard** (`/agent`) — reseller back-office
5. **POS Terminal** (`/pos`) — touch-optimized cashier checkout

## About the Design Files
The files in this bundle are **design references created in HTML/CSS/vanilla JS** — prototypes showing the intended look, layout, and behavior. **They are not production code to copy directly.** Your task is to **recreate these designs in the target codebase's environment** (the brief implies a responsive web app — React is a natural fit, but use whatever the project already uses) following its established component patterns, routing, and state libraries. If no environment exists yet, choose an appropriate stack (e.g. React + a CSS-variable token system, or Tailwind with the tokens mapped into the theme) and implement there.

The HTML is intentionally token-driven and componentized in spirit, so it maps cleanly to a real component library. Treat `assets/system.css` as the source of truth for design tokens.

## Fidelity
**High-fidelity (hifi).** These are pixel-level mockups with final colors, typography, spacing, radii, shadows, and interactions. Recreate the UI faithfully using your codebase's libraries. Exact token values are documented below and defined in `assets/system.css`.

## Theming model (critical)
The platform is **multi-tenant and themeable**. Every brand color derives from a single `--brand` token (plus `-600/-700/-800/-100/-50` ramp). Swapping that one ramp re-skins the entire app:
- **Master/platform screens** default to **Petrol** (teal-blue).
- **Agent screens** default to **Green** (the sample agent "Najd Systems"); each agent picks their own primary at runtime.
- A third **Indigo** theme is included to prove the system.

Implement `--brand` as a runtime-swappable theme (CSS variables on a `[data-theme]` attribute, or a ThemeProvider). Agents should be able to set their own primary/secondary + logo + domain. Neutrals and semantic colors (emerald/amber/violet/sky) stay fixed across themes.

Themes are defined in `assets/system.css` under `:root`, `[data-theme="green"]`, `[data-theme="indigo"]`.

## Internationalization & RTL (critical)
Full **Arabic / Urdu RTL** support is required (also English + Hindi). The prototypes flip layout via `dir="rtl"` on `<html>` and switch the font stack to `--ff-ar` (IBM Plex Sans Arabic). All directional CSS uses logical properties (`margin-inline-start`, `inset-inline-end`, `border-inline-start`) so mirroring is automatic. Numerals use `font-variant-numeric: tabular-nums` and stay LTR. In the prototype the *copy* remains English under RTL (layout-only demo) — production must supply real translated strings per locale.

---

## Design Tokens

> Source of truth: `assets/system.css`. Colors are authored in **OKLCH**; hex approximations given for convenience.

### Brand ramp — Petrol (platform default)
| Token | OKLCH | ~Hex |
|---|---|---|
| `--brand` | `oklch(0.55 0.105 222)` | `#1488A6` |
| `--brand-600` | `oklch(0.49 0.108 224)` | `#0E7693` |
| `--brand-700` | `oklch(0.42 0.098 226)` | `#0D6079` |
| `--brand-800` | `oklch(0.34 0.080 228)` | `#143C4C` (deep / sidebars / footers) |
| `--brand-100` | `oklch(0.93 0.035 222)` | `#D7EBF1` |
| `--brand-50` | `oklch(0.965 0.018 222)` | `#EAF5F8` |
| `--on-brand` | `oklch(0.99 0.005 222)` | `#FAFEFF` (text on brand) |

### Brand ramp — Green (agent default, `[data-theme="green"]`)
`--brand: oklch(0.50 0.105 158)` (~`#1E8A5A`), 800 `oklch(0.31 0.075 160)` (~`#1B4D38`). Same ramp structure.

### Brand ramp — Indigo (`[data-theme="indigo"]`)
`--brand: oklch(0.51 0.18 278)` (~`#5B4BD6`).

### Accent — Gold (fixed across themes)
| `--gold` | `oklch(0.80 0.115 80)` | `#E6B45C` |
| `--gold-600` | `oklch(0.72 0.118 76)` | `#CD9A40` |

### Semantic (fixed across themes)
| Token | Use | OKLCH | ~Hex |
|---|---|---|---|
| `--success` | positive metrics | `oklch(0.62 0.13 158)` | `#23A06B` |
| `--warning` | warnings/amber | `oklch(0.74 0.135 70)` | `#D6A33A` |
| `--violet` | neutral stats | `oklch(0.55 0.15 295)` | `#7B57C9` |
| `--sky` | system health | `oklch(0.64 0.12 232)` | `#3D9AD1` |
| `--danger` | errors/suspended | `oklch(0.57 0.18 22)` | `#D14A3A` |

Each has a matching `-50` tint for soft backgrounds.

### Neutrals (cool slate)
| Token | Use | ~Hex |
|---|---|---|
| `--bg` | app background | `#F3F5F7` |
| `--bg-2` | subtle fills | `#EDF0F2` |
| `--surface` | cards/white | `#FFFFFF` |
| `--line` | borders | `#E4E8EB` |
| `--line-strong` | strong borders | `#D2D8DD` |
| `--text` | primary text | `#363D45` |
| `--text-2` | secondary text | `#5E6670` |
| `--muted` | muted text | `#7E858F` |
| `--faint` | faint/labels | `#A3A9B1` |

### Typography
- **UI / display:** `Hanken Grotesk` (weights 400/500/600/700/800). Headings `letter-spacing: -0.02em`, `line-height: 1.12`, `font-weight: 700`.
- **Data / mono:** `JetBrains Mono` (`--ff-mono`) for invoice numbers, codes, timestamps, eyebrow labels.
- **Arabic / RTL:** `IBM Plex Sans Arabic` (`--ff-ar`).
- Base body: 15px / line-height 1.5.
- Type scale used: hero h1 54px (centered variant 60px), section h2 38px, card h3 17–18px, stat value 28px (800), body 14–17px, labels 11–13px.
- All numeric/currency values: `font-variant-numeric: tabular-nums`.

### Spacing — 8px grid
Scale: `4 / 8 / 12 / 16 / 20 / 24 / 32 / 48`. Card padding 24px; button padding 12px 18px; section vertical padding 88px (marketing).

### Radius
| Token | Value | Use |
|---|---|---|
| `--r-card` | 16px | cards |
| `--r-md` | 12px | inner blocks |
| `--r-sm` | 8px | buttons, inputs |
| `--r-pill` | 999px | chips, badges, pills |

### Shadows
| Token | Value |
|---|---|
| `--sh-sm` | `0 1px 2px oklch(0.45 0.05 250 / .06), 0 1px 1px oklch(0.45 0.05 250 / .04)` |
| `--sh` | `0 4px 6px -1px …/.10, 0 2px 4px -2px …/.07` |
| `--sh-md` | `0 10px 20px -6px …/.13, 0 4px 8px -4px …/.08` |
| `--sh-lg` | `0 24px 48px -12px …/.20, 0 8px 16px -8px …/.10` |

### Icons
Lucide / Feather style, **stroke width 1.75**, rounded line caps/joins, 24×24 viewBox. The prototype hand-rolls a subset in `assets/icons.js` — in production use **lucide-react** (or your icon lib) with the same names where possible (dashboard→layout-dashboard, sar→custom Saudi Riyal glyph, scan, wifi-off, etc.). The Saudi Riyal symbol (`sar`) is a custom glyph — use the official SAR symbol.

---

## Shared Components (build these first)
Derived from `assets/system.css`:
- **Button** — variants: `primary` (brand fill), `gold`, `outline`, `ghost`; sizes `sm / default / lg`; `block`. Radius 8px, weight 600, gap 8px for icon.
- **Card** — surface, 1px `--line` border, radius 16px, `--sh-sm`, 24px padding.
- **Badge / Pill** — pill-shaped status tags. Pill color variants: success / warning / violet / sky / danger / muted (each = `-50` bg + darkened text). Optional leading `.dot`.
- **Chip** — toggleable filter chip; `.active` = brand fill.
- **Stat card** — label + icon swatch (42px rounded square, semantic tint) + 28px/800 value + delta row (up=emerald, down=danger).
- **Switch** — 40×23 toggle, brand fill when checked; RTL-aware thumb travel.
- **Table** — uppercase 11.5px faint headers, 14px rows, hover `--surface-2`, dashed/solid `--line` row borders.
- **Avatar** — 36px circle, brand gradient, white initials.
- **Placeholder (`.ph`)** — 135° striped fill + mono caption pill, for any image slot the developer should replace with real product/marketing imagery.

---

## Screens / Views

### 1. Master Landing — `Master Landing.html` (route `/`)
**Purpose:** Recruit resellers/partners. Sells the *opportunity*, not the product. Theme: Petrol.
**Layout:** Full-width marketing, no sidebar. Sticky blurred nav (logo + links + "Start Your Business" primary CTA). Sections stack at max-width 1180px, 88px vertical padding, alternating `--surface` / `--bg-2` backgrounds; one dark `--brand-800` CTA band.
**Sections & components:**
- **Hero** — 2-col split (1.05fr / 0.95fr). Left: gold badge "Saudi Vision 2030 Partner", h1 54px "Start your own software company.", 19px subhead, primary CTA "Start Your Business Today" + outline "Talk to Sales", trust row with emerald check icons. Right: a **revenue mockup card** (live MRR `SAR 48,200 ↑38%` + an SVG area+line chart + two mini-stats) with a floating "+9 new clients/mo" stat chip and a rotated gold handshake chip. **Hero variation:** `split` (default) vs `center` (centered text, h1 60px, visual below) — controlled by `[data-var-hero]`.
- **Partnership model** — "Your brand. Our technology." 2-col: 3 labeled rows (White-label POS / Full technical support / Keep 100% of client relationships) + two stacked branded landing-page mockups.
- **Why partner** — 4 feature cards (Recurring revenue, Zero coding, Saudi market expertise, 24/7 partner support).
- **How it works** — 4 numbered steps (56px brand circles with dashed connector line) Brand it → Sell it → Onboard merchants → Collect monthly fees.
- **Distributor packages** — 3 pricing cards Starter (SAR 1,490/mo, 25 slots) / **Growth** (SAR 3,900/mo, 100 slots — featured, scaled 1.03, gold "Most popular" tab) / Enterprise (SAR 8,500/mo, 250+ slots). These are what *partners* buy.
- **Testimonials** — 3 quote cards (5 gold stars, quote, avatar + agency, growth stat).
- **Dark CTA band** + **footer** (4-col: brand blurb / Program / Company / Legal, bottom legal row).

### 2. Agent Landing — `Agent Landing.html` (route `/d/:agentId`)
**Purpose:** The reseller's white-label site. Sells the *product* (simplicity, speed). **Themeable** — defaults to Green here; agent logo/colors/domain replace defaults at runtime.
**Layout:** Same marketing scaffold as Master Landing.
**Sections & components:**
- **Hero** — split. Left: badge "Authorized POS Provider", h1 "An easy-to-use POS for your shop.", subhead, primary "Start Free Trial" (agent color) + outline "See Demo", trial trust row. Right: a **live POS terminal mockup** (mini product grid with category chips + cart with line items, VAT line, Total `SAR 60.95`, green Pay button) plus a floating ZATCA QR badge. Same `split`/`center` hero variation.
- **Feature grid** — 3×2 cards: Fast checkout, ZATCA e-invoicing, Inventory management, Multi-language (EN/AR/HI/UR), Real-time reports, Cloud sync.
- **Trust badges** — pill row: ZATCA Certified, Saudi-made, 24/7 Arabic support, GDPR & local compliance, "mada · Visa · Apple Pay".
- **Social proof** — 4-up stat band (98% satisfaction / 5,000+ merchants / 2.3s checkout / 4.9★) + 3 merchant testimonials with stars.
- **Simple pricing** — Basic (SAR 150/mo, 1 branch) / **Pro** (SAR 280/mo, 3 branches — featured) / Premium (SAR 450/mo, unlimited + API). CTA "Start 14-day trial". These are *merchant* subscriptions.
- **Contact CTA band** (dark) with phone/WhatsApp + **footer** with agent brand.

### 3. Master Dashboard — `Master Dashboard.html` (route `/master`)
**Purpose:** Platform owner oversees all agents & economics. Theme: Petrol.
**Layout:** App shell — 256px fixed left sidebar + sticky topbar + scrolling content (max 1320px). Shell CSS in `assets/dashboard.css`.
- **Sidebar** (`--brand-800` bg): brand block; nav groups "Platform" (Dashboard*, Agents [badge 18], Packages) and "Operations" (Audit Log, Notifications [badge 3], Tax Settings, Profile); active item has gold inline-start indicator bar; bottom user box (gold avatar "FA · Faisal Al-Otaibi · Platform Owner").
- **Topbar:** title "Platform Overview" / subtitle "All agents and revenue · June 2026"; right: search icon-btn, bell icon-btn (red dot), "+ Create Agent" primary.
- **4 stat cards:** Total Agents 18 (brand), MRR `SAR 248,600` +11.4% (emerald), Active Packages 12/18 with progress bar (violet), System Health 16/18 active (sky).
- **Quick-action chips:** Packages · Audit Log · Notifications · Tax settings.
- **Platform Economics card:** 6-cell mini-grid (MRR, ARR `SAR 2.98M`, Active Merchants 1,284/1,410, Churn 2.1%, Platform Revenue `SAR 74,580`, Collected YTD `SAR 1.34M`) + **Revenue by Agent leaderboard table** (rank, agent avatar+name+domain, merchants, MRR, share bar, status pill; top 5 ranks in gold).
- **Split row:** MRR 12-month area+line chart card (+ x-axis month labels) + Recent Activity feed (icon + event + mono timestamp).
- **Audit Log card:** 5 rows (mono time tag + actor + action).
- **Layout variations** (`[data-var-layout]`): `split` (chart+activity side by side) vs `stacked`; **density** (`[data-var-density]`): `comfy` vs `compact`.

### 4. Agent Dashboard — `Agent Dashboard.html` (route `/agent`)
**Purpose:** Reseller manages merchants, margin, feature toggles, branding. Theme: Green (`data-theme="green"` on `<html>`). Header shows agent brand name; buttons use agent primary.
**Layout:** Same app shell.
- **Sidebar** (`--brand-800` green): brand "Najd Systems / AGENT WORKSPACE"; nav Dashboard*, Clients [214], Branding Editor, Subscription Toggles, Reports, Profile; a "Switch to Master view" link; user box "SN · Sara Al-Nasser · Reseller Admin".
- **Topbar:** title "Najd Systems POS" / subtitle "Clients · 214 merchants…"; gold "White-label active" badge, bell, "+ Add Client" primary.
- **4 stat cards:** Total Clients 214 (brand), Monthly Revenue `SAR 48,200` (emerald), Active Subscriptions 198/214 (violet), Remaining Slots 36 of 250 (amber).
- **Revenue & Margin card:** 3-cell grid — Collected `SAR 48,200`, Owed to platform `SAR 13,800` (amber), Net margin `SAR 34,400` (emerald).
- **Main grid (1fr / 320px):** left = **Client List table** (avatar+name+business, plan pill, status pill, monthly fee SAR, joined date, manage-features + view icon buttons) with search field + status filter chips; right column = **Feature overrides card** for a selected client (5 switches: Inventory, Discounts, Loyalty program, ZATCA e-invoice, Email receipts) + **White-label look card** (branded preview, 3 color swatches, "Edit branding" button).
- **Layout variation** (`[data-var-layout]`): `split` (sidebar column) vs `full` (full-width, right cards become 2-up); density same as Master.

### 5. POS Terminal — `POS Terminal.html` (route `/pos`)
**Purpose:** Cashier rings up a sale fast. **Touch-optimized for tablet landscape.** CSS in `assets/pos.css`.
**Layout:** Full-viewport two-panel grid, **no sidebar**, page does not scroll (panels scroll internally). Left panel = product selection (`1fr`); right = cart/checkout (`420px`). **Variation:** cart on right (default) or left (`[data-var-panel]`).
- **Left top bar:** amber "Offline — syncing" indicator (wifi-off), search input ("Scan barcode or search products…"), brand "Scan" button.
- **Category chip row:** All / Hot Drinks / Cold Drinks / Pastries / Meals / Desserts / Retail (active = brand fill), horizontal scroll.
- **Product grid:** responsive auto-fill tiles (min 150px; **dense** variant 120px; **list** variant = horizontal rows). Each tile: tinted thumb with category icon, name, price (SAR). In-cart tiles show a brand quantity badge + brand border. Min tap target ~132px tall. Tile variations via `[data-var-tiles]`: `comfy / dense / list`.
- **Right cart panel:**
  - Header "Current Sale" + count pill, "Hold" button (parks sale), clear-cart trash.
  - **Line items:** thumb, name + unit price, **−/qty/+ stepper**, line total, trash. Empty state with cart icon.
  - Footer: discount code input + Apply; **tip buttons** (No tip / 5 / 10 / 15%); **summary** (Subtotal, Discount line, Tip line, VAT 15%, **Total** 26px/800); **payment method picker** (Cash / Card / Split); secondary "Loyalty" + "Gift card"; large full-width **Pay** button (shows total, disabled when empty).
  - **Extra controls row:** Refund · No sale · Display · Receipts.
- **Receipt overlay (post-payment):** centered modal, emerald success header with check, invoice meta (mono INV number, date, cashier, items, total), **ZATCA e-Invoice QR box** (QR placeholder + VAT number), Print / PDF / New Sale actions.

---

## Interactions & Behavior

### POS Terminal (the only stateful screen — fully working in the prototype)
State: `cart` (map of productName → {qty}), `activeCat`, `discount` (rate), `discCode`, `tipPct`, `method`, `invNo`.
- **Add to cart:** tap tile → increment qty, re-render grid (badge) + cart + totals.
- **Qty stepper:** −/+ adjusts qty; qty ≤ 0 removes the line.
- **Category filter & search:** filter product grid live.
- **Discount codes:** `WELCOME10`=10%, `EID15`=15%, `STAFF20`=20%; invalid → clears + "Invalid code" placeholder.
- **Tips:** percentage of taxable amount.
- **Math (Saudi VAT):** `discountAmt = subtotal × rate`; `taxable = subtotal − discountAmt`; `tip = taxable × tipPct`; `VAT = taxable × 0.15`; `total = taxable + VAT + tip`. (Tip is not taxed.)
- **Pay:** opens receipt overlay, generates `INV-00####`, renders a deterministic ZATCA QR placeholder. **New Sale** increments invoice no. and resets cart.
- **Hold:** parks the sale (prototype shows confirmation, then resets the button).
Reference implementation: inline `<script>` in `POS Terminal.html`.

### All screens — prototype chrome (NOT for production)
A floating "prototype toolbar" (`assets/proto.js`) drives **layout variations**, **theme switching**, and the **RTL toggle**. This is a demo affordance — **do not ship it**. Instead:
- Variations → resolve to the single chosen production layout (confirm with design which variant is canonical per screen; the defaults shown are the recommended ones).
- Theme → a real ThemeProvider / per-tenant theme.
- RTL → real i18n + `dir` handling.

### Marketing screens
- Sticky nav with backdrop blur; cards lift on hover (`translateY(-3px)` + larger shadow); featured pricing card scaled.
- Charts are inline SVG (area gradient + 2.5px line + endpoint dot). In production use a chart lib (Recharts/visx) fed real series.

### Transitions
Buttons/cards: `all .14–.18s ease`. Primary buttons lift 1px on hover. Switch thumb 0.18s. Keep subtle.

## State Management
Only the POS Terminal needs real local state (cart + checkout math above). Dashboards are data-driven reads (fetch agents/clients/metrics → render cards, tables, charts). Marketing pages are static + a theme context. Per-tenant theming and locale/`dir` are app-level context/providers.

## Responsive behavior
- Dashboards: sidebar hides < 860px; stat row 4→2 cols < 1080px; split panels stack < 1080px.
- Marketing: hero & grids collapse to 1–2 cols < 940px; step connectors hide.
- POS: panels stack to rows < 820px (cart capped ~46vh). Primary target is tablet landscape.

## Assets
- **Icons:** custom Lucide/Feather-style set in `assets/icons.js` (stroke 1.75). Replace with `lucide-react` or equivalent; provide a proper **Saudi Riyal (SAR)** glyph.
- **Imagery:** none shipped — all image areas use the striped `.ph` placeholder or composed CSS/SVG mockups (revenue card, POS mockup, branded-site mockups). Replace with real product photos, agent logos, and marketing imagery.
- **ZATCA QR:** the QR in receipts/badges is a **deterministic visual placeholder** (`makeQR()` in `assets/proto.js`). Production must render a real **TLV-encoded ZATCA QR** (seller name, VAT number, timestamp, invoice total, VAT amount) generated server-side.
- **Fonts:** Google Fonts — Hanken Grotesk, JetBrains Mono, IBM Plex Sans Arabic.

## Files
Design references in this bundle:
- `index.html` — design-system overview + navigation hub (not a product screen; useful as a token/spec reference)
- `Master Landing.html`
- `Agent Landing.html`
- `Master Dashboard.html`
- `Agent Dashboard.html`
- `POS Terminal.html`
- `assets/system.css` — **design tokens + shared component styles (source of truth)**
- `assets/dashboard.css` — dashboard app-shell styles
- `assets/marketing.css` — landing-page styles
- `assets/pos.css` — POS terminal styles
- `assets/icons.js` — icon set + `icon(name)` helper
- `assets/proto.js` — QR placeholder + prototype toolbar (demo chrome — do not port)

Open any HTML file in a browser to interact with it. The POS Terminal is fully clickable; every screen's floating toolbar toggles layout variants, theme, and RTL.
