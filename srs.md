# Software Requirements Specification (SRS) — v2.0

## Saudi Unified-Commerce POS Platform — Multi-Tenant, White-Label, ZATCA-Compliant

**Version:** 2.0 (vision-grade rewrite)
**Date:** 2026-06-03
**Supersedes:** v1.0 (the original feature-checklist SRS). v2.0 re-frames the product around **market-expected behavior** — what a POS in the Saudi market must do to stand next to the category leaders — not just the minimal flows of v1.0. Every v1.0 requirement ID is preserved; v2.0 adds new requirement families and raises the completion bar.

---

## 0. How to read this document

This SRS is the **source of truth for the *vision*, not the current code**. It deliberately specifies more than is built today. That is intentional: the downstream completeness loop (`prompts.md` → `INTENDED_BEHAVIOR.md` → `COMPLETENESS_REVIEW.md`) measures the code against *this* vision, so every gap between "what the market expects" and "what exists" surfaces as a tracked, fixable finding. **"Complete" means "a Saudi merchant or reseller would choose this over Foodics / Rewaa / Marn,"** not "the buttons render."

Requirement IDs are stable and grouped by family (e.g. `PAY-03`, `RST-07`). Each requirement carries a **priority**: `P0` (table-stake — the product is not market-credible without it), `P1` (expected in a serious product), `P2` (competitive differentiator). Where a requirement encodes a behavior the market expects but the SRS previously omitted, it is tagged `[market]`.

---

## 1. Introduction

### 1.1 Purpose

Define the requirements for a **modern, unified-commerce Point-of-Sale platform** for the Saudi/GCC market that:

- serves **both retail and restaurant** merchants from one product (catalog/inventory commerce *and* table/kitchen/restaurant operations);
- is **ZATCA Phase-2 compliant** (cryptographic stamping, hash-chained sequencing, TLV QR, Fatoora reporting/clearance, 6-year retention);
- accepts payment the way Saudi customers actually pay: **Mada, Apple Pay, STC Pay, BNPL (Tabby/Tamara), cash, card**, via integrated payment terminals and Saudi gateways;
- is **bilingual-first (Arabic/RTL)** with full ar/en/hi/ur localization, and renders **all fiscal documents in Arabic** regardless of UI language;
- is delivered as a **three-tier white-label SaaS**: **Master** (platform owner) → **Agent** (white-label reseller) → **Client** (merchant), where each client sees only their agent's brand;
- works **offline-first** and never loses a sale.

### 1.2 Vision / North Star

> A reseller in Riyadh signs up, white-labels the platform to their own brand and domain in an afternoon, and onboards a restaurant *and* a retail shop under the same login. The restaurant runs tables, sends orders to the kitchen display, and accepts Mada and Apple Pay at the table. The shop scans barcodes, manages multi-branch stock, and reconciles its drawer with a Z-report at close. Every sale is a real ZATCA-cleared Arabic invoice. The merchant pays the reseller monthly; the reseller pays the platform; everyone sees their own clean dashboard. Nothing on screen says "POS template."

The product is judged against the Saudi category leaders. Where this SRS is silent, **the default is "do what Foodics/Rewaa/Marn do, localized for Saudi."**

### 1.3 Scope

- One multi-tenant backend + database; horizontally scalable.
- Five surfaces: **Master Dashboard**, **Agent Dashboard**, **Client/Merchant Back-Office**, **POS Terminal** (retail + restaurant modes), and **Customer-Facing Display**.
- ZATCA Phase-2 e-invoicing (B2B clearance + B2C reporting).
- Saudi payment rails + integrated terminals + online checkout.
- Unified retail and restaurant operations.
- White-label depth: branding, custom domain, branded email, branded mobile (PWA now, native roadmap).
- Subscription billing, dunning, and master↔agent revenue/commission accounting.
- Full design system: every page, dashboard, and **printable** (receipt, A4 invoice, credit note, quotation, Z/X report, kitchen ticket, barcode/shelf label) is specified.

### 1.4 Definitions & Acronyms

| Term | Definition |
|------|------------|
| **ZATCA / Fatoora** | Saudi Zakat, Tax and Customs Authority; Fatoora is its e-invoicing platform. |
| **Phase 2 (Integration)** | Mandatory e-invoicing phase requiring cryptographic stamp, CSID, and reporting/clearance to Fatoora. |
| **Clearance vs Reporting** | B2B **standard** tax invoices are *cleared* (submitted to Fatoora in real time, returned stamped); B2C **simplified** invoices are *reported* within 24h. |
| **CSID** | Cryptographic Stamp Identifier (compliance + production), issued by ZATCA from a CSR. |
| **PIH / ICV** | Previous Invoice Hash / Invoice Counter Value — the per-client hash chain. |
| **TLV** | Tag-Length-Value encoding used for the ZATCA QR. |
| **Mada** | Saudi national debit network — the dominant card rail (**70%+ of card transactions**); must be a first-class tender, routed via a Mada-certified local acquirer. |
| **STC Pay / urpay** | Saudi mobile wallets. |
| **Tabby / Tamara** | Saudi BNPL ("buy now, pay later") providers. |
| **Moyasar / Tap / HyperPay / PayTabs / Geidea / Amazon Payment Services** | Saudi/GCC payment gateways & acquirers. |
| **SoftPOS / Tap-to-Pay** | Accepting card/wallet taps directly on a phone, no separate terminal. **In KSA today this is Android-only (e.g. Geidea SoftPOS); Tap-to-Pay on iPhone is not yet launched in Saudi as of 2026 — treat as roadmap.** |
| **KDS** | Kitchen Display System — screen in the kitchen showing live orders. |
| **KOT** | Kitchen Order Ticket — the printed/displayed prep order. |
| **Z-report / X-report** | End-of-shift fiscal close (Z) / mid-shift snapshot (X): sales by tender, VAT, voids, refunds, cash variance. |
| **PDPL** | Saudi Personal Data Protection Law. |
| **White-label / Agent / Client / Package** | Reseller branding; reseller; merchant; prepaid block of client licenses. |
| **Aggregator** | Food-delivery marketplace (HungerStation, Jahez, ToYou, Mrsool, Keeta). |
| **Omnichannel** | Selling across POS + e-commerce (Salla, Zid) with shared catalog/stock. |

---

## 2. Market & Competitive Context

### 2.1 Who we are measured against

| Segment | Reference products | What they set as the baseline |
|---------|--------------------|-------------------------------|
| **Restaurant POS (KSA)** | **Foodics** (category leader), Marn, Anypay | Tables/floor plan, KDS, modifiers/combos, course timing, aggregator integration, Mada/Apple Pay at table, Arabic-first, ZATCA. |
| **Retail POS (KSA)** | **Rewaa**, Marn | Barcode, variants/matrix, multi-branch stock, purchase orders, stock counts, supplier/COGS, e-commerce sync, ZATCA. |
| **Payments-led POS (KSA)** | **Geidea**, Marn, Mada terminals | Integrated Mada terminal, SoftPOS, settlement reporting. |
| **Global baselines** | Square, Loyverse, Lightspeed, Shopify POS, Odoo POS | Offline-first, clean UX, app marketplace, reporting depth, hardware ecosystem. |
| **Reseller / white-label SaaS** | White-label POS programs, Stripe-Billing-class tooling | Deep branding (domain, email, app), dunning/proration, commission/revenue-split reporting, merchant impersonation/support. |

### 2.2 Jobs-to-be-done → implied intended behavior (the market layer)

These tables are the conceptual heart of the spec: a market expectation on the left, the **behavior it obligates** on the right. Requirement IDs in §3 implement them.

**Cashier (retail) / Server (restaurant)**

| Expectation | Implied intended behavior | IDs |
|-------------|---------------------------|-----|
| Charge a card by tapping an integrated **Mada/Apple Pay terminal**, not typing an amount | Checkout pushes the total to a connected terminal, waits for approval, stamps the **approval code + RRN + network** onto the invoice; decline blocks the sale | PAY-01..PAY-06 |
| Sub-second checkout that never dies offline | Sale commits locally with no network; queue + auto-sync; idempotent replay | POS-05, POS-12 |
| Park/hold a ticket and recall it; run several open tickets/tables | Sale has `held`/`open` states; multi-ticket and table-bound orders | POS-10, RST-01..RST-04 |
| Variants, modifiers, combos, weighted & open-price items | Line items support variants, modifier groups, combo pricing, sale-time price, qty-by-weight | INV-04, RST-05, POS-11 |
| Partial & line-level refunds, exchanges | Refund supports partial/line-level and item exchange, each a ZATCA credit note | POS-07, POS-13 |

**Merchant owner**

| Expectation | Implied behavior | IDs |
|-------------|------------------|-----|
| See **profit**, not just revenue | Reports compute COGS & margin per item/category; dead-stock & reorder reports | RPT-04, INV-09 |
| Fiscal day-close (**Z-report**) | Shift close emits a structured Z-report (sales by tender, VAT, voids, refunds, cash variance) | RPT-06, POS-09 |
| Hand off to accounting | Standard journal export + **Zoho/QuickBooks/Odoo** sync; ZATCA-clean | FIN-01..FIN-04 |
| Sell online too (Salla/Zid) and on aggregators | Shared catalog/stock; online & aggregator orders appear on POS; stock reconciles | OMN-01..OMN-05, RST-08 |
| Promotions, gift cards, store credit | Discounts beyond %/flat; gift-card issue/redeem; store credit | PRC-01..PRC-06 |

**Agent / reseller**

| Expectation | Implied behavior | IDs |
|-------------|------------------|-----|
| **Deep** white-label, not just colors | Custom **domain**, branded **email sender/templates**, branded app, branded printables | AG-05..AG-09 |
| Run a real billing business | **Dunning** (retry/grace/reminders) before suspension; proration; plan change; merchant invoices | CL-06..CL-10 |
| Know their **margin** | **Commission/revenue-split ledger**: merchant-paid, master-owed, agent-net — as a report | RSL-01..RSL-04 |
| Support their merchants | **Impersonate / log in as merchant**; reset password; merchant health | RSL-05..RSL-07 |
| Self-service growth | Public **sign-up funnel** per agent that provisions a trial client end-to-end | AG-10, CL-11 |

**Master / platform operator**

| Expectation | Implied behavior | IDs |
|-------------|------------------|-----|
| Operate multi-tenant SaaS safely | Tenant isolation, audit, **backups/DR**, metering, rate limiting, observability, migrations | SEC-*, OPS-* |
| Enterprise-sellable compliance | **PDPL** handling, PCI-scope minimization (PANs never touch us), ZATCA conformance evidence | SEC-05..SEC-08 |
| Platform economics | Global MRR, churn, active-merchant counts, agent revenue rollup | RSL-08, RPT-09 |

**End customer (shopper / diner)**

| Expectation | Implied behavior | IDs |
|-------------|------------------|-----|
| A valid **ZATCA invoice** with scannable QR, emailed/SMS on request | Arabic fiscal invoice + QR; email/SMS delivery | ZA-02, ZA-03, POS-04 |
| Pay how Saudis pay | Mada, Apple Pay, STC Pay, **BNPL**, cash | PAY-01..PAY-04 |
| See the order/total on a screen | Customer-facing display reflects live cart, total, and paid state | UX-08 |

---

## 3. System Features & Requirements

> Legend — Priority: **P0** table-stake · **P1** expected · **P2** differentiator. `[market]` = added in v2.0 from market expectation (absent or thin in v1.0).

### 3.1 Master / Agent Management (Master Dashboard) — `MA`

| ID | Pri | Requirement |
|----|-----|-------------|
| MA-01 | P0 | Master creates an agent (company, email, phone, package 10/50/100) — provisions a login **and** the agent record in one step; one-time temp password surfaced. |
| MA-02 | P0 | System deducts one client slot when an agent provisions a client (atomic, cannot oversell). |
| MA-03 | P0 | Master sees real-time used vs. remaining slots per agent. |
| MA-04 | P0 | Master refills/raises an agent's slot allowance. |
| MA-05 | P0 | Master sets the global VAT rate (and ZATCA env); agents/clients inherit and cannot override. |
| MA-06 | P1 | Master can suspend/reactivate and (soft-)delete an agent; suspension blocks the agent and (configurably) cascades to the agent's clients. |
| MA-07 | P1 `[market]` | Master defines packages (slots, wholesale price, suggested retail) and plan entitlements (which feature tiers a package unlocks). |
| MA-08 | P1 `[market]` | Master dashboard shows platform economics: total agents, active clients, MRR, churn, revenue by agent (→ RSL-08). |
| MA-09 | P1 `[market]` | Master configures global ZATCA gateway credentials and toggles sandbox/simulation/production per environment. |

### 3.2 White-Labeling & Feature Entitlement (Agent Dashboard) — `AG`

| ID | Pri | Requirement |
|----|-----|-------------|
| AG-01 | P0 | Agent uploads logo (PNG/JPEG/WebP/SVG, ≤2 MB) — stored and served. |
| AG-02 | P0 | Agent sets primary/secondary color, font family, button radius, favicon, default language. |
| AG-03 | P0 | Agent enables/disables features per client (and as a default), and the toggle **actually gates** the capability server-side. |
| AG-04 | P0 | On client login (web/mobile), the UI loads the agent's theme dynamically; no platform brand is ever shown. |
| AG-05 | P1 `[market]` | **Custom domain / subdomain** per agent (e.g. `pos.agentbrand.com`), with the merchant login and public funnel served under it. |
| AG-06 | P1 `[market]` | **Branded transactional email**: agent's sender name, reply-to, logo, and templates for provisioning, receipts, dunning. |
| AG-07 | P1 `[market]` | **Branded printables**: agent/client logo, header/footer, and contact details on receipts, invoices, quotations (within ZATCA layout rules). |
| AG-08 | P2 `[market]` | **Branded mobile app** (PWA installable now; native white-label app on roadmap). |
| AG-09 | P1 `[market]` | Agent payment settings: connect the agent's Saudi gateway/Stripe-Connect account for **collecting client subscriptions** and (optionally) for clients' own card acceptance. |
| AG-10 | P2 `[market]` | Agent **public landing/funnel** page (per-agent, branded) with pricing and a trial-signup CTA that provisions a client. |

### 3.3 Client Onboarding, Subscription & Billing — `CL`

| ID | Pri | Requirement |
|----|-----|-------------|
| CL-01 | P0 | Agent creates a client → system provisions the **merchant's own** login (temp password, `must_change_password`), sends a branded email with login link + temp password, decrements a slot. |
| CL-02 | P0 | Client picks language and business type (**retail / restaurant / both**) during first-login setup. |
| CL-03 | P0 | Agent sets the client's subscription fee and cycle (monthly/yearly). |
| CL-04 | P0 | Client views and **pays** subscription via the agent's gateway; payment is recorded and the billing date advances; decline does not advance and surfaces an error. |
| CL-05 | P0 | On non-payment the agent (or an automated job) can suspend the client; suspension blocks the merchant at auth. |
| CL-06 | P1 `[market]` | **Dunning**: before suspension, the system retries the charge on a schedule and sends branded reminders (grace period configurable). |
| CL-07 | P1 `[market]` | **Proration & plan change**: upgrading/downgrading a client mid-cycle prorates the next invoice. |
| CL-08 | P1 `[market]` | The system issues the **merchant a subscription invoice** (the agent→client B2B invoice), ZATCA-compliant where the agent is VAT-registered. |
| CL-09 | P1 `[market]` | Client billing history shows invoices, payment method, and downloadable receipts. |
| CL-10 | P2 `[market]` | Usage-based add-ons (extra branches/terminals/API volume) meter and bill on top of the base fee. |
| CL-11 | P2 `[market]` | Self-service trial signup from the agent funnel (AG-10) creates a trial client with an expiry and conversion prompt. |

### 3.4 POS Terminal — Core / Retail — `POS`

| ID | Pri | Requirement |
|----|-----|-------------|
| POS-01 | P0 | Cart: add items (scan/search/grid), set quantity, line & cart discounts, tax. |
| POS-02 | P0 | Multiple & **split** tenders in one sale: cash, card, Mada, wallet, BNPL, loyalty, gift card, store credit; record the breakdown. |
| POS-03 | P0 | Produce a **ZATCA-compliant Arabic invoice** (thermal + A4) with embedded TLV QR; print, PDF, and on-screen. |
| POS-04 | P0 | Send invoice/receipt via email/SMS (feature-gated). |
| POS-05 | P0 | **Offline-first**: sales commit locally and sync when online (idempotent, no double-post), incl. ZATCA QR assignment on sync. |
| POS-06 | P0 | Product search by **barcode (hardware scanner + camera)** or name (ar/en). |
| POS-07 | P0 | Return/refund with a ZATCA **credit note** — supporting **partial and line-level** refunds and exchanges. |
| POS-08 | P1 | Cart-level operations: void line, void sale (audited), price override (permissioned), customer attach, note. |
| POS-09 | P0 `[market]` | **Shift/drawer**: open with float, pay-in/pay-out, cash-drop, close with counted cash → reconciliation; sales accrue to the open shift. |
| POS-10 | P1 `[market]` | **Park/hold & recall**: suspend a sale and resume it; multiple concurrent open tickets. |
| POS-11 | P1 `[market]` | **Weighted & open-price** items (scale integration or manual weight; price entered at sale). |
| POS-12 | P0 `[market]` | Offline cap & conflict policy explicit (≥500 queued sales; deterministic conflict handling on sync). |
| POS-13 | P2 `[market]` | **Tips** capture (line/percentage), recorded per tender and reportable (restaurant + service retail). |
| POS-14 | P1 | Quick-keys / favorites grid and category navigation tuned for touch (tablet). |

### 3.5 Restaurant Operations — `RST` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| RST-01 | P0 | **Floor/table map** per branch: zones, tables, seats; table states (free/occupied/bill-printed). |
| RST-02 | P0 | **Order types**: dine-in (table), takeaway, delivery; each drives tax/printing/flow rules. |
| RST-03 | P0 | Open a table order, add/fire items by course, transfer table, merge/split bills, split by seat/amount/item. |
| RST-04 | P1 | **Bill before payment**: print a non-fiscal "check" (طلب/فاتورة مبدئية), then settle to a ZATCA invoice on payment. |
| RST-05 | P0 | **Modifiers & combos**: required/optional modifier groups, add-on pricing, combo/meal bundles. |
| RST-06 | P0 | **KDS / KOT**: fire items to a Kitchen Display and/or kitchen printer by prep-station; bump/recall; ticket timing. |
| RST-07 | P1 | Course coordination (starters → mains), hold-and-fire, all-day item counts for the kitchen. |
| RST-08 | P1 `[market]` | **Aggregator orders** (Jahez/HungerStation/Talabat/Keeta) ingest into the POS/KDS and reconcile into sales & stock — **via middleware (Deliverect-class) or a Delivery Hero POS-partner integration. There are no direct public merchant APIs for the aggregators; do not plan against them.** |
| RST-09 | P2 | Recipe/ingredient **inventory depletion** (a sold dish deducts its recipe components). |
| RST-10 | P2 | Service charge handling (e.g. optional %) distinct from VAT, ZATCA-correct. |

### 3.6 Payments (Saudi-real) — `PAY` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| PAY-01 | P0 | **Mada** as a first-class tender; the invoice records the network (Mada/Visa/Mastercard) and approval/RRN. |
| PAY-02 | P0 | **Apple Pay** and **STC Pay** (and urpay) supported as tenders. |
| PAY-03 | P0 | **BNPL**: Tabby and Tamara as tenders (online checkout + in-store where supported). |
| PAY-04 | P0 | Cash, card, bank transfer, and split across any of the above in one sale. |
| PAY-05 | P0 | **Integrated payment terminal**: push the amount to a connected Mada/card terminal and capture the approval onto the invoice; decline blocks the sale. **In-store capture is via an acquirer terminal SDK — Geidea (Android SoftPOS + physical terminals) is the primary KSA path; the online gateways in PAY-06 do *not* provide in-store terminal capture.** |
| PAY-06 | P1 | **Gateway abstraction — two distinct surfaces:** (a) **online** payments / links / hosted checkout via **Moyasar** (recommended first — SAMA-licensed, strongest KSA docs, Mada/Apple Pay/STC Pay), Tap, HyperPay, or PayTabs; (b) **in-store terminal / SoftPOS** via **Geidea (Android SDK)**. Pluggable per agent/client; do not assume one provider covers both surfaces. |
| PAY-07 | P1 | **Online payment links / hosted checkout** for invoices, quotations-to-invoice, and subscriptions. |
| PAY-08 | P1 | **Settlement & payout reporting**: per-tender totals reconcilable against the gateway/acquirer settlement. |
| PAY-09 | P0 | **PCI scope minimization**: card PANs are entered on the terminal/gateway, never on our servers; we store only tokens/last-4/network. |
| PAY-10 | P2 | Refunds routed back to the **original tender** (card refund to card, BNPL refund to BNPL) where the gateway supports it. |

### 3.7 Inventory & Catalog Depth — `INV` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| INV-01 | P0 | Products: name (ar/en), barcode/SKU, price, cost, VAT rate, category, image, active. |
| INV-02 | P0 | Categories (hierarchical), units of measure, tax class. |
| INV-03 | P0 | **Multi-branch stock** ledgers; per-branch quantity, branch-scoped sales/reports. |
| INV-04 | P1 | **Variants/matrix** (size/color), each a sellable SKU with its own barcode/stock. |
| INV-05 | P1 | **Stock transfers** between branches with send/receive states and audit. |
| INV-06 | P1 | **Stock counts / adjustments** with reasons (count, wastage, damage), producing a variance record. |
| INV-07 | P0 | **Purchase orders**: create, receive (full/partial) into a branch, set cost, update COGS; supplier ledger. |
| INV-08 | P1 | **Low-stock alerts & reorder points** per product/branch; optional auto-PO suggestion. |
| INV-09 | P1 | **COGS & valuation** (moving average or FIFO) feeding margin reports. |
| INV-10 | P2 | Composite/bundle products and recipe BOM (ties to RST-09). |
| INV-11 | P1 | Bulk import/export (CSV) for catalog, stock, customers, with validation and error report. |

### 3.8 Customers, Loyalty & Marketing — `CRM` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| CRM-01 | P0 | Customer records: name, phone, email, VAT number (for B2B invoices), notes, purchase history. |
| CRM-02 | P0 | **Loyalty**: points accrual/redemption tied to customers, configurable rate, gated by feature. |
| CRM-03 | P1 | **Gift cards & store credit**: issue, redeem, balance, expiry (ties to PRC-05). |
| CRM-04 | P1 | Customer **segments/tags** and lifetime value (RFM-lite). |
| CRM-05 | P1 | **SMS/WhatsApp marketing** campaigns (promotions, receipts, win-back) — consent-aware (PDPL). |
| CRM-06 | P2 | House accounts / credit customers with statements. |

### 3.9 Pricing & Promotions — `PRC` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| PRC-01 | P0 | Discounts: percentage & fixed, line & cart, min-purchase, validity, usage caps, permissioned. |
| PRC-02 | P1 | Coupon/promo codes; auto-applied promotions (e.g. happy-hour, time-window). |
| PRC-03 | P1 | **BOGO / quantity-break / bundle** promotions. |
| PRC-04 | P1 | Customer-/segment-specific & branch-specific pricing and price lists. |
| PRC-05 | P1 | Gift-card issuance/redemption as a tender (with CRM-03). |
| PRC-06 | P2 | Scheduled price changes and cost-plus margin pricing. |

### 3.10 Reporting & Analytics — `RPT` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| RPT-01 | P0 | Sales summary by period (day/week/month), revenue, txn count, average order. |
| RPT-02 | P0 | Top/bottom products, by category, by branch, by cashier/server, by hour (heatmap). |
| RPT-03 | P0 | **Payment-method breakdown** (cash/Mada/card/wallet/BNPL/loyalty) per period. |
| RPT-04 | P1 | **Profit & COGS / margin** reports; dead-stock and slow-movers. |
| RPT-05 | P1 | Tax/VAT report (output VAT, by rate) supporting VAT return filing. |
| RPT-06 | P0 | **Z-report / X-report** (shift close/snapshot): tenders, VAT, discounts, voids, refunds, cash variance, payouts. |
| RPT-07 | P1 | Inventory reports: on-hand value, movements, transfers, adjustments. |
| RPT-08 | P1 | Refund/void report; discount report (who/when/why). |
| RPT-09 | P1 | Agent/master economics: MRR, active clients, churn, revenue by agent (with RSL). |
| RPT-10 | P1 | **CSV + PDF export** for every report; scheduled email digests (P2). |

### 3.11 Accounting & Finance — `FIN` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| FIN-01 | P1 | Expense tracking (category, amount, date, attachment) and revenue-vs-expense view. |
| FIN-02 | P1 | **Accounting export**: standard journal / general-ledger CSV (sales, VAT, COGS, payments). |
| FIN-03 | P2 | **Integrations**: Zoho Books, QuickBooks, Odoo (push invoices/journal). |
| FIN-04 | P1 | Cash management: drawer movements, payouts, petty cash tie to shift (with POS-09). |
| FIN-05 | P2 | Supplier payments / accounts payable basics. |

### 3.12 Omnichannel — `OMN` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| OMN-01 | P1 | **Salla** integration: shared catalog & stock, import online orders. |
| OMN-02 | P1 | **Zid** integration: shared catalog & stock, import online orders. |
| OMN-03 | P1 | Online orders appear in the back-office (and POS/KDS for restaurant) and **decrement the same stock**. |
| OMN-04 | P2 | Unified customer & loyalty across channels. |
| OMN-05 | P2 | Click-and-collect / online-order fulfilment status. |

### 3.13 ZATCA Compliance — `ZA` (Critical)

| ID | Pri | Requirement |
|----|-----|-------------|
| ZA-01 | P0 | Onboarding: generate CSR, obtain compliance + production CSID from Fatoora, store certificate & secret **encrypted (AES-256)**. |
| ZA-02 | P0 | Every invoice carries seller name, VAT number, timestamp, totals, VAT total, and a **real cryptographic stamp** (ECDSA, Phase 2). |
| ZA-03 | P0 | QR is **TLV-encoded** with all mandatory tags (incl. hash, stamp, public key). |
| ZA-04 | P0 | Invoices are **per-client sequential** (counter + ICV) and **hash-chained** (PIH) — tamper-evident. |
| ZA-05 | P0 | Signed documents **retained ≥6 years**. |
| ZA-06 | P0 | **Clearance vs reporting** routing: B2B **standard** invoices cleared in real time; B2C **simplified** invoices reported within 24h (background job, retry). Detect standard vs simplified by invoice type — **note B2B supplies < 1,000 SAR may also be issued as simplified**, so do not route purely on buyer type. |
| ZA-07 | P1 | Sandbox/simulation/production environments selectable; onboarding usable by agents/clients. |
| ZA-08 | P1 | **Operational visibility**: a dashboard of documents by status (signed/reported/cleared/failed/pending) with alerts on stuck `pending`/`failed`. |
| ZA-09 | P1 | Per-client `zatca_enabled` policy is explicit and intentional (always-on vs optional-per-client) and the UI reflects it. |
| ZA-10 | P1 | Integrity check: walk the chain, verify each stamp and `previous_hash`, and report the first break. |

### 3.14 Reseller Platform Economics — `RSL` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| RSL-01 | P1 | **Commission/revenue-split ledger**: for each subscription payment, record merchant-paid, master's cut, agent's net. |
| RSL-02 | P1 | Agent revenue report: total collected, master owed, net margin, by period and by client. |
| RSL-03 | P1 | Master revenue report: owed-by-agent, collected, outstanding. |
| RSL-04 | P2 | Automated payout/settlement between agent and master (or statement for manual settlement). |
| RSL-05 | P1 | **Merchant impersonation / "log in as"** for support, fully audited. |
| RSL-06 | P0 | Agent can reset a client's password and re-issue credentials. |
| RSL-07 | P1 | Merchant health view (last activity, sales trend, subscription status) for the agent. |
| RSL-08 | P1 | Platform-wide economics for master (MRR, churn, active merchants, agent leaderboard). |

### 3.15 Multi-Language & Localization — `L10N`

| ID | Pri | Requirement |
|----|-----|-------------|
| L10N-01 | P0 | UI strings in ar/en/hi/ur; **every key present in every locale** (no silent English fallback in shipped screens). |
| L10N-02 | P0 | **RTL** layout for Arabic & Urdu (mirrored UI, right-aligned). |
| L10N-03 | P0 | Arabic-Indic digits for ar/ur; Western for en/hi; SAR currency formatting. |
| L10N-04 | P1 | Gregorian required; **Hijri** display optional. |
| L10N-05 | P0 | Agent sets a default language; client can override; persists per user. |
| L10N-06 | P0 | **All fiscal documents (receipt, invoice, credit note, quotation) render in Arabic** regardless of UI language (ZATCA §7). |

### 3.16 Hardware — `HW` `[market]`

| ID | Pri | Requirement |
|----|-----|-------------|
| HW-01 | P0 | **Thermal receipt printers** via ESC/POS (WebUSB/Bluetooth/network) with embedded QR. |
| HW-02 | P0 | **Barcode scanners** (USB HID + camera). |
| HW-03 | P0 | **Integrated payment terminal** (with PAY-05). |
| HW-04 | P1 | **Cash drawer** kick (via printer). |
| HW-05 | P1 | **Customer-facing display** (second screen). |
| HW-06 | P1 | **Kitchen printer / KDS screen** (restaurant). |
| HW-07 | P2 | **Weighing scale** integration (grocery). |
| HW-08 | P2 | **Label/barcode printer** for shelf & product labels. |

### 3.17 Security, Privacy & Compliance — `SEC`

| ID | Pri | Requirement |
|----|-----|-------------|
| SEC-01 | P0 | Passwords bcrypt-hashed; JWT access + refresh; server-side logout/revocation; session timeout. |
| SEC-02 | P0 | **Tenant isolation / row-level scoping**: client sees only own data; agent only their clients; verified, not assumed. |
| SEC-03 | P0 | **Granular RBAC**: per-staff permissions (refunds, reports, price override, voids, product edits); deny-wins; master bypass. |
| SEC-04 | P0 | ZATCA keys & gateway secrets encrypted at rest (AES-256), never logged. |
| SEC-05 | P1 | **PDPL** compliance: consent capture for marketing, data-subject export/delete, data-residency awareness. |
| SEC-06 | P1 | **PCI-DSS scope minimization** (PAY-09); no PAN storage. |
| SEC-07 | P0 | **Audit trail completeness**: every authenticated mutation logged (actor, entity, change, ip), immutable-ish, out-of-band. |
| SEC-08 | P1 | Rate limiting, input validation/sanitization on all endpoints, CORS lockdown to production origins. |

### 3.18 Operations & Reliability — `OPS`

| ID | Pri | Requirement |
|----|-----|-------------|
| OPS-01 | P0 | **Database migrations** (Alembic) — schema via versioned migrations, not runtime ALTER. |
| OPS-02 | P0 | **Transaction atomicity**: a sale's invoice-counter, inventory, loyalty, shift, and ZATCA sign commit in one transaction; any failure rolls back wholly. |
| OPS-03 | P1 | **Backups & point-in-time recovery**; documented restore. |
| OPS-04 | P1 | **Observability**: Sentry (FE+BE), structured logs, health checks, slow-query/perf monitoring, uptime alerts. |
| OPS-05 | P0 | **Server-side pagination** on every list endpoint (no load-everything). |
| OPS-06 | P1 | **Global search** across products/customers/transactions. |
| OPS-07 | P1 | API metering / rate plans tied to package (with CL-10). |
| OPS-08 | P1 | Graceful degradation: every integration (gateway/ZATCA/email/SMS/storage) degrades to a logged/queued fallback, never crashing the request. |

### 3.19 Design System & Printables — `UX` / `PRN` `[market]`

> Full per-page and per-printable design lives in `INTENDED_BEHAVIOR.md`. The SRS fixes the *requirements*; the behavior model fixes the *design*.

| ID | Pri | Requirement |
|----|-----|-------------|
| UX-01 | P0 | A single **design system** (tokens: color from agent brand, type, spacing, radius) applied across all surfaces; RTL-correct. |
| UX-02 | P0 | Every page defines its **states**: loading, empty, error, permission-denied, offline. No dead-ends. |
| UX-03 | P0 | **Touch-optimized POS** (tablet) and responsive back-office (desktop/tablet/mobile). |
| UX-04 | P1 | Consistent navigation per role (master/agent/client) with role-correct menus. |
| UX-05 | P1 | Onboarding/first-run guidance per role. |
| UX-06 | P1 | Accessibility: contrast, focus, keyboard, screen-reader labels (ar/en). |
| UX-07 | P0 | **Customer-facing display** screen (live cart, total, paid, branded). |
| UX-08 | P1 | Notification center (low-stock, ZATCA-failed, subscription, KDS) — persisted. |
| PRN-01 | P0 | **Thermal receipt** (80mm): Arabic, branded, ZATCA QR, tenders, VAT, cashier/shift. |
| PRN-02 | P0 | **A4 tax invoice** (Arabic, ZATCA-compliant) — print & PDF. |
| PRN-03 | P0 | **Credit note** (type 381) Arabic, referencing the original invoice. |
| PRN-04 | P0 | **Quotation / عرض سعر** (Arabic, clearly **non-fiscal**). |
| PRN-05 | P0 | **Z-report / X-report** printable. |
| PRN-06 | P1 | **Kitchen ticket (KOT)** per station (restaurant). |
| PRN-07 | P1 | **Barcode / shelf label** (retail). |
| PRN-08 | P1 | **Subscription invoice** (agent→client) and dunning notices. |
| PRN-09 | P0 | All printables: Arabic-Indic digits, SAR, RTL, branded header/footer, retained where fiscal. |

---

## 4. External Interface Requirements

### 4.1 User interfaces
Master, Agent, and Merchant back-office (responsive web, RTL); POS Terminal (touch/tablet, retail + restaurant modes); Customer-Facing Display (second screen); installable PWA (offline); native white-label app on roadmap.

### 4.2 Hardware interfaces
ESC/POS thermal printers (WebUSB/Bluetooth/network); barcode scanners (USB HID + camera `BarcodeDetector`); integrated Mada/card terminals & SoftPOS; cash drawer (printer-kick); customer display; kitchen printer/KDS; scale; label printer. (See `HW`.)

### 4.3 Software interfaces
- **Payments (online):** Moyasar (recommended first), Tap, HyperPay, PayTabs; Apple Pay, STC Pay, urpay; Tabby, Tamara (BNPL). **In-store terminal/SoftPOS:** Geidea (Android SDK) — a *separate* integration surface from the online gateways. (See `PAY`.)
- **ZATCA:** Fatoora API (compliance/production CSID, reporting, clearance); UBL 2.1 invoices; ECDSA stamping. **Validate hashing/QR-TLV/stamp against ZATCA's official SDK**, not a bespoke implementation alone.
- **Email/SMS/WhatsApp:** SMTP/SendGrid, Twilio/Unifonic (KSA), WhatsApp Business.
- **E-commerce:** Salla (public OAuth2 Merchant API + webhooks), Zid (partner API). **Aggregators:** Jahez, HungerStation, Talabat, Keeta — **via middleware (Deliverect) or Delivery Hero POS-partner program; no direct public merchant APIs.**
- **Accounting:** Zoho Books, QuickBooks, Odoo.
- **Storage:** S3-compatible for logos/certificates/exports.

### 4.4 Communication interfaces
REST/JSON; WebSocket/SSE for real-time (KDS, offline sync, live dashboards); HTTPS/TLS 1.2+ only; webhooks (HMAC-signed) for outbound events.

---

## 5. Non-Functional Requirements

### 5.1 Performance
- Online sale commit ≤ 1 s; offline sync replay ≤ 5 s after reconnect.
- Dashboards load ≤ 2 s at 10,000 clients; lists paginated server-side (OPS-05).
- KDS updates within ~1 s of order fire.

### 5.2 Security — see `SEC`. bcrypt, JWT access+refresh+revocation, row-level tenancy, granular RBAC, AES-256 secret-at-rest, PDPL, PCI-scope minimization, complete audit, rate-limit + CORS lockdown.

### 5.3 Scalability
Stateless backend, shared PostgreSQL, cache (Redis) for branding/settings; 100+ agents × 100 clients to start; horizontally scalable; tenant-aware.

### 5.4 Availability
99.9% for core POS APIs; **offline mode guarantees POS never stops**; degraded-dependency fallbacks (OPS-08).

### 5.5 Multi-Tenancy & White-Labeling
Tenant resolved per request from DB membership (not JWT); dynamic theme (CSS variables) + logo per tenant; **no hardcoded brand**; custom domain per agent (AG-05).

---

## 6. Data Model Overview (key entities, expanded)

Beyond v1.0 (agents, agent_features, clients, client_features, packages, products, categories, customers, transactions, discounts, expenses, suppliers, purchase_orders, staff_members, shifts, branches, product_branch_stock, loyalty_programs, loyalty_points, receipt_templates, webhooks, audit_logs, permissions, api_usage, subscription_payments, system_settings, revoked_tokens, zatca_credentials, zatca_documents, quotations), v2.0 adds (illustrative):

```
payment_tenders        (transaction_id, type[mada|applepay|stcpay|tabby|tamara|cash|card|loyalty|giftcard], amount,
                        network, approval_code, rrn, gateway_ref, last4, token)
payment_accounts       (owner[agent|client], gateway, credentials_enc, is_active)        -- PAY-06
terminals              (client_id, branch_id, type, serial, gateway, status)             -- PAY-05/HW-03
tables / floor_zones   (branch_id, name, seats, state)                                   -- RST-01
order_tickets          (client_id, branch_id, table_id?, order_type, state[open|held|fired|settled], course_state)  -- RST/POS-10
modifiers / modifier_groups / combos                                                     -- RST-05
kds_tickets / prep_stations                                                              -- RST-06
product_variants       (product_id, attributes, sku, barcode, price, stock)              -- INV-04
stock_transfers / stock_counts / stock_adjustments                                       -- INV-05/06
gift_cards / store_credit                                                                -- CRM-03/PRC-05
price_lists / promotions / coupons                                                       -- PRC
commission_ledger      (subscription_payment_id, agent_id, gross, master_cut, agent_net) -- RSL-01
channel_orders         (source[salla|zid|hungerstation|jahez|...], external_id, status)  -- OMN/RST-08
custom_domains         (agent_id, hostname, status)                                      -- AG-05
email_templates        (owner, key, subject, body, branding)                             -- AG-06
notifications          (user_id, type, payload, read_at)  -- persisted                   -- UX-08
```

(Exact schema is implementation-defined; this overview fixes intent. Schema changes go through **Alembic migrations**, OPS-01.)

---

## 7. ZATCA Implementation Notes

- **Per-client onboarding:** generate EC key + CSR → compliance CSID (CSR + OTP) → production CSID; store all secrets AES-256-encrypted; mark `onboarded`.
- **Invoice generation (in the sale transaction):** build UBL 2.1 (388 invoice / 381 credit note with billing reference + PIH) → compute hash → **ECDSA stamp** → advance PIH/ICV → write `zatca_documents` (retained 6y) → stamp TLV QR onto the txn.
- **Standard (B2B) vs simplified (B2C):** detect from invoice type, not buyer type alone — **B2B supplies < 1,000 SAR may also be issued as simplified**. **Standard → clearance** (real-time submit, store cleared XML); **simplified → reporting** within 24h via background job with retry. **Validate the hash chain, QR/TLV, and signature against ZATCA's official SDK.**
- **Default-install reality must be intentional:** if onboarding/gateway are unconfigured, signing still happens locally and reporting fails-closed to `pending` — but ZA-08 requires this state to be **visible and alertable**, not silent.
- **All fiscal output is Arabic** (L10N-06).

---

## 8. Sample User Flows

**Agent onboards a restaurant client (unified):** agent creates client → branded email + temp password → client first-login picks Arabic + "restaurant" → sets up floor/tables, menu with modifiers, KDS station, connects Mada terminal → ready to serve.

**Server rings a dine-in sale:** open table → add items by course → fire to KDS → print check → settle (Mada terminal tap + split with cash) → ZATCA simplified invoice (Arabic + QR) printed → table freed → reported to Fatoora in background.

**Retail sale with online stock:** cashier scans items → applies a coupon → charges Apple Pay → stock decrements the same pool Salla sells from → Arabic invoice + QR.

**B2B sale:** customer with VAT number selected → **standard** invoice → **cleared** by Fatoora in real time → Arabic A4 invoice emailed.

**Refund:** select original → partial/line-level refund → ZATCA **credit note** (381) → original tender refunded (PAY-10) → stock restored → shift netted.

**Shift close:** count drawer → **Z-report** (tenders incl. Mada/Apple Pay/cash, VAT, voids, refunds, variance) printed.

**Subscription & economics:** client pays agent (gateway) → commission ledger records master-cut/agent-net → agent sees margin; master sees MRR.

---

## 9. Roadmap / Phasing

Priorities order the build but the **vision is the whole document**. Suggested phasing (the completeness loop will refine):

- **Phase A (market-credible core):** all **P0** in POS, PAY, ZA (incl. ZA-06 clearance/reporting), INV, SEC, OPS, L10N, PRN P0; RST P0 if a restaurant client exists.
- **Phase B (serious product):** P1 across RST, INV, CRM, PRC, RPT (Z-report, margins), CL dunning/proration, RSL revenue-split, AG custom domain/email, FIN export.
- **Phase C (differentiators):** P2 — omnichannel, accounting integrations, aggregators, advanced analytics, branded native app, usage billing.

---

## 10. Assumptions & Dependencies

- Agents hold their own Saudi gateway/acquirer accounts; master provides ZATCA sandbox guidance.
- ZATCA production CSIDs require a valid Saudi VAT registration per client.
- Card PANs are handled by certified terminals/gateways; we are out of PCI cardholder-data scope (PAY-09/SEC-06).
- Aggregator/e-commerce integrations depend on third-party API availability.
- Native app store approval for a generic white-label app is a known dependency (AG-08).

---

## 11. Appendix — Glossary highlights
CSID (compliance/production stamp identifier) · PIH/ICV (hash-chain) · TLV (QR encoding) · ECDSA (stamp) · KDS/KOT (kitchen) · Z/X report (fiscal close) · Mada/STC Pay/Tabby/Tamara (Saudi rails) · PDPL (privacy law) · Clearance/Reporting (B2B/B2C ZATCA routing).

---

**This SRS is the vision blueprint.** It is intentionally ahead of the code. The gap between it and the running system is the backlog the completeness loop exists to discover, verify, and close — until a Saudi merchant or reseller would pick this over the incumbents.
