# AI Workflow-Completeness Prompts — v2.0 (vision-anchored)

> **What changed in v2.0.** The loop no longer measures the code against a thin feature checklist. It measures the code against a **market-parity vision** (`srs.md` v2.0): a unified retail + restaurant, Saudi-real-payments, ZATCA-compliant, white-label POS that a merchant or reseller would choose over **Foodics / Rewaa / Marn**. "Complete" = *that*, not "the buttons render." Consequently `INTENDED_BEHAVIOR.md` now also carries a **market-expectation baseline**, **per-page/dashboard/printable design specs**, and an **orphaned-scaffolding** ledger; Prompt 2 reports **market & design gaps** as first-class findings; Prompt 3 builds **to the design**, not just to "something appears."

> **Document map.** `srs.md` (the **vision** — requirements + market layer, with families MA-/AG-/CL-/POS-/RST-/PAY-/INV-/CRM-/PRC-/RPT-/FIN-/OMN-/ZA-/RSL-/L10N-/HW-/SEC-/OPS-/UX-/PRN-) · `CLAUDE.md` (architecture, conventions, **and the product North Star**) · `RUN.md` (run standalone) · `INTENDED_BEHAVIOR.md` (behavior + design model — **produced by Prompt 1**) · `COMPLETENESS_REVIEW.md` (verified gap/parity report = remediation backlog — **produced by Prompt 2**, consumed by Prompt 3) · **this file** (reusable prompts).

The loop, unchanged in shape, sharpened in bar: **build the vision model → review code against it → close each gap.** The first two catch incompleteness **against the market vision** (a flow the SRS now demands but the code lacks: no Mada terminal, whole-invoice-only refunds, no Z-report, no commission ledger, a dead-end page, a printable that isn't ZATCA-Arabic, an orphaned MGX router). The third drives the fix sessions, building **to the specified design**.

> The discover/verify pairing is the point — **AI discovers candidate gaps (wide, fallible); deterministic tests verify them (narrow, durable).** The vision is large on purpose; expect a long backlog. That is the plan, not a failure.

## How to use

1. **Build the vision model.** Fresh session at the repo root → **Prompt 1** → produces `INTENDED_BEHAVIOR.md`: the market-expected behavior baseline, the per-feature flows (incl. every v2.0 family), the **design spec for every page/dashboard/printable**, the state machines, and the orphaned-scaffolding ledger — all cross-mapped to `srs.md` IDs.
2. **Review against the model.** Another fresh session → **Prompt 2** → audits the code against `INTENDED_BEHAVIOR.md` (behavior **and** design **and** market parity) → writes `COMPLETENESS_REVIEW.md`.
3. **Close the loop.** For every *confirmed* finding, build it **to the design** and promote it to a deterministic artifact (Playwright E2E, `pytest` contract test, or a traceability row mapping the SRS ID → the test). AI finds it once; the test catches it always.

> Notes: AI review is **non-deterministic** — re-runs surface different findings. Run Prompt 2 **per feature family** for depth (POS sale + ZATCA atomicity, PAY Saudi tenders + terminal, RST restaurant ops, agent→client provisioning + revenue split, white-label depth), not just whole-app. Always keep `CLAUDE.md` + `srs.md` + `INTENDED_BEHAVIOR.md` in context so "complete" means **the vision**, not the model's priors. Treat output as a prioritized backlog of suspicions, never a release gate. **Vision over code:** when the code and the SRS disagree, the SRS wins and the delta is a finding — never downgrade the spec to match the code.

---

## Prompt 1 — Build the vision model of intended behavior (`INTENDED_BEHAVIOR.md`)

Paste into a fresh session opened at the repo root.

````text
You are producing a precise, exhaustive **vision model of intended behavior AND design** for this codebase and writing it to `INTENDED_BEHAVIOR.md` at the repo root.

## Why this file exists
It is the ground-truth used later by AI review to detect **incompleteness against the market vision** — not just "is the SRS checkbox built" but "does the product behave and look like a market-credible Saudi POS a merchant/reseller would choose over Foodics/Rewaa/Marn." A gap detector is only as good as its notion of "complete" — this file IS that notion. So it must describe **intended behavior and intended design** (what *should* happen and what each screen/printable *should* be), grounded in `srs.md` v2.0 (which already encodes the market layer). Where the code diverges from this vision, that divergence is exactly what a future reviewer must catch — capture the intent, then note where the code falls short.

## The product, in one breath
A multi-tenant, white-label SaaS POS for the Saudi market: **Master → Agent (reseller) → Client (merchant)**. It serves **both retail and restaurant** from one product, takes **Saudi-real payments** (Mada, Apple Pay, STC Pay, BNPL Tabby/Tamara, cash, split) via **integrated terminals**, is **ZATCA Phase-2** compliant (real ECDSA stamp, hash chain, TLV QR, clearance for B2B / reporting for B2C, 6-year retention), is **Arabic/RTL-first** (all fiscal docs Arabic regardless of UI language), works **offline-first**, and is **deeply white-labeled** (brand, domain, email, printables). The bar is **parity with the KSA leaders**.

## First, orient yourself (read before writing)
1. `CLAUDE.md` — architecture & conventions AND the **Product North Star**: three-tier tenancy (role derived per request from DB membership, not the JWT, in `backend/routers/tenant.py::get_user_role`); the per-entity CRUD triad (`routers/`+`services/`+`models/<entity>.py`) with `/all` and `/batch` conventions and service-layer `user_id` scoping; router auto-discovery in `main.py`; the hand-written routers carrying real logic (`tenant.py`, `pos.py`, `zatca.py`, `payment.py`, etc.).
2. `srs.md` v2.0 — the **vision** SRS. It numbers every feature family and carries a **§2.2 market layer** (jobs-to-be-done → implied intended behavior) and **priorities (P0/P1/P2)**. Reuse its IDs. Don't restate it verbatim — the SRS says "what is required (and why the market expects it)"; yours says "what the running system must concretely do and how each screen/printable must look, traced through the code."
3. `RUN.md` — how the app boots (standalone uvicorn + static frontend; master seeded from env; tables/seed on startup).
4. The actual code, end to end: `backend/routers|services|models|core`, `frontend/src/pages|components|contexts|lib`. Trace real flows front→back (page → `src/lib/api.ts` → `atomsClient.ts` → router → service → model/DB → side effects: inventory, ZATCA QR/stamp, payment tender, audit, loyalty, slot decrement, KDS fire). **Inventory every router and every page** — you must account for each as either a feature section or an orphan.

## Rules
- **Vision over code.** Describe what the system *should* do and look like per `srs.md` v2.0 and the market. Where the code is thinner (e.g. "card" with no Mada/terminal; whole-invoice-only refund; no Z-report; no commission ledger; no restaurant mode; a printable in the UI language instead of Arabic), document the **intended** behavior/design and flag the shortfall inline + in "Open questions / gaps."
- **Be exhaustive.** Cover every SRS family (§3.1–3.19) AND every entity with a real workflow AND cross-cutting behavior (tenancy, theming, RTL/i18n, audit, atomicity, graceful degradation). Cover **retail and restaurant** both.
- **Make "complete" explicit.** Every feature has **Completion criteria** — concrete, checkable assertions tied to SRS IDs ("A card sale pushes the amount to the terminal, captures the approval, and stamps RRN+network onto the invoice; a decline blocks the sale" — PAY-05).
- **Cover the full flow graph**, not just happy paths: permission-denied, not-found, validation, empty, slot-exhausted, gateway/terminal-declined/unconfigured, ZATCA clearance-vs-reporting, offline/sync, degraded dependency.
- **Capture state machines** (states + transitions + trigger + actor): agent, client, subscription (incl. dunning/past_due), package slots, transaction (sale/held/refunded/partial-refund/credit-note/synced), order_ticket (open/held/fired/settled — restaurant), shift (open/closed), purchase_order, stock_transfer, ZATCA onboarding, ZATCA document (signed/reported/cleared/failed/pending), payment tender, gift card.
- **Distinguish fact from inference.** Mark `(inferred)` and add to "Open questions." Do not invent. Be especially careful with ZATCA (real stamp vs local-only reporting), payments (is a tender real or a label?), and restaurant (is any of it built?).
- **Diffable & maintainable:** stable headings, short declarative sentences, tables for matrices and for design component lists.

## Required structure of INTENDED_BEHAVIOR.md
1. **Header + purpose** — what this file is; that it models the **vision** (parity bar), behavior **and** design; how the review uses it.
2. **Table of contents.**
3. **Two-products framing** — make explicit that this is (A) a POS for merchants and (B) a white-label SaaS platform for resellers/operator, each judged against a different competitor set and each with its own completion bar.
4. **Market-expected behavior baseline** — reproduce/refine `srs.md` §2.2 as actor→expectation→implied-behavior tables (cashier/server, merchant owner, agent, master, end customer), each row tagged `table-stake | differentiator` and a current status `built | shallow | absent | orphaned` with evidence. This is the layer that makes "complete" mean "market-credible."
5. **Global model:** Actors & roles (how each is derived) · Permission/scope matrix (triad single-record vs `/all` vs `/batch`; granular RBAC keys; feature flags) · **State-machine catalog** (all lifecycles in one place) · Cross-cutting invariants (tenancy scoping; no-hardcoded-brand; **all fiscal docs Arabic**; server-stamped IDs; sale atomicity incl. payment+ZATCA; slot integrity; global-tax inheritance; PCI scope minimization; every integration degrades).
6. **Per-feature sections**, numbered to match `srs.md` families (3.1 MA, 3.2 AG, 3.3 CL, 3.4 POS, 3.5 RST, 3.6 PAY, 3.7 INV, 3.8 CRM, 3.9 PRC, 3.10 RPT, 3.11 FIN, 3.12 OMN, 3.13 ZA, 3.14 RSL, 3.15 L10N, 3.16 HW, 3.17 SEC, 3.18 OPS, 3.19 UX/PRN). Template per feature:

   ```
   ### <SRS family/id> <Feature name> — <key files> (cite SRS IDs + priority)
   **Purpose:** one line.
   **Market expectation vs SRS vs code:** what the market demands · what SRS requires · what the code currently does (built/shallow/absent/orphaned).
   **Actors & permissions:** master/agent/client/staff + permission keys + feature flags.
   **Entities & states:** data + lifecycle states/transitions.
   **Primary flow (happy path):** numbered front→back steps (page → api.ts → router → service → DB → side effects), each precondition → action → postcondition.
   **Alternate / edge flows:** permission-denied, not-found, validation, empty, slot-exhausted, terminal/gateway declined or unconfigured, ZATCA clearance/reporting, offline/sync, degraded dependency.
   **Side effects & integrations:** inventory, payment tender capture, ZATCA QR/stamp + counter, KDS fire, audit, loyalty, slot decrement, commission ledger, webhooks, email/SMS.
   **Cross-feature dependencies.**
   **Completion criteria:** checkable "complete when…" assertions, each tied to an SRS ID and its priority. Include market-parity criteria, not just SRS-minimum.
   **Open questions / gaps:** inferred/ambiguous items + where code falls short of the vision.
   ```

7. **Page & dashboard design specs** — for EVERY screen (Master Dashboard, Agent Dashboard, Branding Editor, Agent funnel/landing, Client back-office dashboard, POS Terminal retail mode, POS Terminal restaurant mode + floor/table + KDS, Products/Catalog, Variants, Categories, Inventory/Stock counts/Transfers, Purchase Orders/Suppliers, Customers/Loyalty/Marketing, Discounts/Promotions/Gift cards, Reports/Analytics (+Z-report), Shifts, Branches, Staff & Permissions, Quotations, Webhooks, Audit, Notifications, Subscription/Billing, Revenue/Commission, Settings, User Profile, Customer-Facing Display, Force-Reset, Login). For each, specify:

   ```
   #### <Page name> (route, role) — SRS IDs
   **Goal & primary user task.**
   **Layout:** regions (header/nav/content/side), responsive + RTL behavior, touch vs desktop.
   **Key components:** the concrete controls/widgets (tables, dialogs, cards, the cart, the tender panel, the floor map, the KDS columns…), with the data each shows.
   **States:** loading · empty · error · permission-denied · offline — what each renders. No dead-ends.
   **Actions → endpoints:** every button/control mapped to the API it calls.
   **Design intent:** density, hierarchy, what must be one-tap, brand-token usage.
   ```

8. **Printable specs** — for EVERY printable (PRN-01..PRN-09: thermal receipt 80mm, A4 tax invoice, credit note, quotation, Z/X report, kitchen ticket KOT, barcode/shelf label, subscription invoice, dunning notice). For each: paper/size, Arabic/RTL + Arabic-Indic digits, branded header/footer, the exact fields/sections in order, ZATCA elements (QR/stamp/seller VAT/totals) where fiscal, and the non-fiscal marking where applicable. State the global invariant: **all fiscal documents render in Arabic regardless of UI language.**

9. **End-to-end journeys** — the cross-feature flows as ordered step lists: master→agent onboarding; agent white-label (brand/domain/email) + provision client; **restaurant dine-in sale** (table→KDS→check→Mada terminal split→ZATCA simplified→reported); **retail sale** (scan→coupon→Apple Pay→ZATCA→stock); **B2B standard invoice cleared**; partial/line refund→credit note→tender refund; shift open→sales→Z-report close; offline sale→sync→QR; subscription pay→commission ledger→agent margin & master MRR; omnichannel order decrements shared stock.

10. **Orphaned / unwired scaffolding ledger** — every router/service/page that is built but has no reachable caller or no UI (candidates seen historically: AI Hub `aihub.py`, object storage `storage.py`, Stripe Checkout `payment.py` generic, blog pages, OAuth callback). For each: what it is, evidence of no caller, and a verdict request (dead vs intended). This section is high-value — the review uses it directly.

11. **Completeness-review usage note** — tell the future reviewer: for each feature verify every Primary-flow step, state transition, side effect, Completion criterion, **page-design element**, and **printable field**; report any that has no implementation (dead-end, missing handler, unwired integration, ZATCA/payment façade, design mismatch, non-Arabic fiscal doc, market table-stake absent) as a finding citing the spec item AND the SRS ID. Before reporting, try to refute (the triad + auto-discovery already provide generic CRUD; many models use `extend_existing=True`).

## Output
- Write the whole thing to `INTENDED_BEHAVIOR.md` at the repo root. Structural prose in English; Arabic for UI strings/receipt/quotation content where the product renders Arabic (note explicitly: fiscal docs are Arabic-only per ZATCA).
- At the end, print a short summary: features documented, pages designed, printables specified, entities with state machines, the orphan ledger count, and the top "Open questions / gaps" — calling out the **biggest market gaps** (e.g. Saudi payments/terminal reality, restaurant mode existence, partial refunds, Z-report, commission ledger, white-label depth, ZATCA clearance-vs-reporting) for human confirmation.
````

---

## Prompt 2 — Vision-parity completeness review (`COMPLETENESS_REVIEW.md`)

Paste into a fresh session opened at the repo root **after** `INTENDED_BEHAVIOR.md` exists. To audit a single family, append e.g. `Scope: only 3.6 PAY` or `Scope: only restaurant (RST)`.

````text
You are auditing this codebase for **incompleteness against the market-parity vision** — flows, behaviors, screens, and printables the vision (`srs.md` v2.0 + `INTENDED_BEHAVIOR.md`) demands but the code lacks or only fakes: dead-end UI, missing endpoints, unwired calls, missing state transitions, missing side effects, partial CRUD, stubs/TODOs, **payment/ZATCA façades**, **missing restaurant mode**, **design mismatches**, **non-Arabic fiscal docs**, **absent market table-stakes**, or code that diverges from intended behavior. You write a gap report to `COMPLETENESS_REVIEW.md` at the repo root.

## Inputs / preconditions
- `INTENDED_BEHAVIOR.md` MUST exist at the repo root (the vision model). If missing, STOP and say "run Prompt 1 first." Do not invent a spec.
- Load `CLAUDE.md` (conventions + North Star) and `srs.md` v2.0 (IDs + priorities + market layer). "Complete" means the **vision/parity** bar, not the v1.0 minimum.

## Scope
- Default: audit EVERY feature family + every page-design spec + every printable spec in `INTENDED_BEHAVIOR.md`.
- If the user names a family/screen, audit only that, in depth. Per-family runs are more reliable than whole-app sweeps — for critical areas (POS+ZATCA atomicity, PAY Saudi tenders/terminal, RST restaurant ops, tenancy/RBAC, agent→client provisioning + revenue split, white-label depth) do them one at a time.

## Method (repeat per feature/screen/printable)
1. Load the spec section: Primary-flow steps, state machine, side effects, Completion criteria, **page-design elements**, **printable fields**, and the **market-expectation row** (table-stake vs differentiator).
2. For EACH item, locate the implementing code across the full chain: frontend control/handler → `src/lib/api.ts` (and `atomsClient.ts`) → router (`backend/routers/*`) → service (`backend/services/*`) → model (`backend/models/*`) → side effect (inventory, payment tender capture, ZATCA QR/stamp+counter, KDS fire, audit, slot decrement, commission ledger). Actually open and read the files; trace front to back.
3. Classify each item: ✅ implemented (cite `file:line`) / ⚠️ partial / ❌ missing / ❓ unverifiable.
4. Raise a finding for anything not fully ✅, with a taxonomy label:
   - `DEAD_END_UI` — control with no handler / silent no-op.
   - `MISSING_ENDPOINT` — frontend (or a required SRS action) has no route.
   - `UNWIRED_CALL` / `ORPHAN_CODE` — built capability with no reachable caller/UI (use the orphan ledger).
   - `MISSING_TRANSITION` — a spec state with no code path (e.g. order_ticket "held", subscription "past_due/dunning", transaction "partial-refund").
   - `MISSING_SIDE_EFFECT` — required effect not fired (sale not deducting stock; invoice with no ZATCA QR/stamp/counter; card sale not capturing terminal approval; client-create not decrementing a slot; mutation with no audit; refund with no credit note; subscription pay with no commission-ledger row).
   - `PARTIAL_CRUD` — diverges from the triad (missing delete/`/all`/`/batch`/scoping where siblings have it).
   - `STUB_TODO` — placeholder/TODO/NotImplemented/hardcoded mock/commented-out core (watch a ZATCA "stamp" that's a static string, or a "Mada"/tender that's just a label with no gateway/terminal).
   - `MARKET_GAP` — a market **table-stake** the vision requires that is absent or only cosmetic (e.g. no Mada terminal integration, whole-invoice-only refunds, no Z-report, no commission ledger, no restaurant floor/KDS, no custom domain). Cite the SRS ID + that it's a table-stake.
   - `DESIGN_GAP` — the screen/printable is missing a specified layout region, state (empty/loading/error/offline), component, or action→endpoint mapping; or a fiscal printable renders non-Arabic / lacks QR/stamp.
   - `SPEC_DIVERGENCE` — code does something materially different from the vision (receipt in UI language instead of Arabic; tax rate overridable by agent; ZATCA QR missing TLV tags; B2B not cleared).
   - `UNVERIFIABLE` — cannot confirm from static reading.

## Verification pass (mandatory — this is what makes the report trustworthy)
Before reporting ANY finding, actively try to REFUTE it:
- Search the whole repo for an alternate implementation under another name, a generic/shared handler, the triad CRUD template, router auto-discovery, or a convention that already covers it. Remember many models use `extend_existing=True`; generic CRUD is provided by the triad — don't flag a "missing" endpoint auto-discovery already mounts.
- Only report findings you could NOT refute. For each, state what you searched and why you remain confident.
- Default to NOT reporting when unsure — put it under "Low-confidence / needs human check."
- **No hallucination:** every confirmed finding cites concrete evidence (`file:line`). Never claim complete OR broken without tracing the code.
- Distinguish a **real façade** from a missing feature: a "Mada" button that records a tender label but never talks to a terminal/gateway is `STUB_TODO`/`MARKET_GAP`, not "implemented."

## Output — write `COMPLETENESS_REVIEW.md`
1. **Summary table:** family (SRS id) | spec items | ✅ | ⚠️ | ❌ | ❓ | findings | # of which are P0 table-stakes.
2. **Confirmed findings**, each: ID (`F-001`); the family + exact violated spec item (quote it) + SRS ID + priority; taxonomy label; what's missing/wrong and how it manifests to which actor; evidence `file:line` (+ what you searched to rule out an alternate impl); **Severity + Confidence**; suggested fix; **"Make it catchable forever"** (Playwright E2E / pytest contract / traceability row).
3. **Low-confidence / needs human confirmation.**
4. **Verified-complete** — items fully mapped to real code (auditable both ways).
5. **Parity scorecard** — per family, a one-line "how close to KSA-leader parity" (P0 table-stakes built vs total).

## Rubrics
- **Severity:** `BLOCKER` (core flow unusable / data loss / security / tenant leak / ZATCA non-compliance blocking legal sale / a P0 table-stake absent) · `MAJOR` (feature visibly incomplete or a step silently fails — inventory not deducted, terminal approval not captured, fiscal doc non-Arabic) · `MINOR` (edge/alt-flow/cosmetic) · `INFO`.
- **Confidence:** `HIGH` (traced end-to-end, refutation failed) · `MEDIUM` · `LOW`.

## Finish
Print counts per severity, the P0-table-stake gap count, and the top BLOCKER/MAJOR findings. Remind the operator: a prioritized backlog of suspicions for human review and test-promotion, not a release gate.
````

---

## Prompt 3 — Remediate one finding, build to the design (`COMPLETENESS_REVIEW.md`)

Run **one finding per session**, then commit and `/clear` before the next. Paste into a fresh session at the repo root. `COMPLETENESS_REVIEW.md` **is** the backlog (confirmed findings, ordered by severity, P0 table-stakes first). To target one, append `Finding: F-003`.

````text
You are implementing EXACTLY ONE finding from `COMPLETENESS_REVIEW.md`, then committing and stopping so the operator can `/clear` and start the next in a clean context. One finding, one commit, one session. No batching.

The backlog is `COMPLETENESS_REVIEW.md` (from Prompt 2). If it doesn't exist, STOP and say "run Prompt 2 first." No separate plan file.

## Select the finding
1. Read `COMPLETENESS_REVIEW.md` → "Confirmed findings."
2. If the operator named an ID, use it. Otherwise pick the **highest-severity unfixed** finding (BLOCKER > MAJOR > MINOR > INFO; P0 table-stakes break ties); skip ones marked done.
3. If the fix needs a product decision the report flags as ambiguous — especially **ZATCA scope** (clearance vs reporting; onboarding reality), **payment provider choice** (which Saudi gateway/terminal SDK), or **restaurant scope** — STOP and ask the operator. Do not guess.

## Load context (read before changing anything)
- The finding block (violated spec item, evidence `file:line`, taxonomy label, suggested fix, the named test).
- The cited spec in `INTENDED_BEHAVIOR.md` — implement to the **intended behavior AND the page/printable design** (layout, states, components, action→endpoint), not just "make something appear" — and the matching SRS ID + priority in `srs.md` v2.0.
- `CLAUDE.md` — follow conventions exactly: the entity CRUD triad; `/all` + `/batch`; service-layer `user_id` scoping; inline Pydantic schemas; `src/lib/api.ts` + `atomsClient.ts` call style; role-gated routes in `src/App.tsx` (`ProtectedRoute allowedRoles`); shadcn/ui primitives under `@/components/ui`; the design system / brand tokens (no hardcoded brand); i18n keys added to EVERY locale in `src/lib/i18n.ts` (ar/en/hi/ur) with **RTL checked for ar/ur**; and the invariant that **receipts/invoices/credit-notes/quotations are ALWAYS Arabic per ZATCA**. Match the surrounding generated style (verbose try/except, debug logging). Do NOT edit `index.html`. Schema changes go through **Alembic migrations** (OPS-01), not runtime ALTER.

## Implement (scope discipline)
- Change ONLY what this finding requires. No drive-by refactors. Note adjacent issues at the end for a future session.
- Build to the **design spec**: render every specified state (loading/empty/error/permission-denied/offline), wire every action→endpoint, respect RTL and brand tokens. A screen that renders but is missing its empty/error states is not done.
- For payment/ZATCA findings: integrate the real dependency behind the graceful-degradation pattern (OPS-08) — a tender must capture a real approval (or be clearly sandboxed), a stamp must be real ECDSA, not a string. If a third-party SDK/credential is required and absent, implement the abstraction + sandbox path and STOP to flag the credential need.
- Reuse existing components/dialogs/helpers. Apply across near-identical triad siblings consistently.

## Verify (must pass before committing)
- Add the **deterministic test** the finding names ("Make it catchable forever"): Playwright E2E / pytest contract / unit. It must fail before and pass after. If no test harness exists yet and this is the first such task, set up the minimal harness and say so.
- Gates green: `pnpm run lint`, `pnpm run build` (in `frontend/`), `pytest` (in `backend/`). Backend boots via `python main.py` and still seeds (tables, master account). If you added a migration, it applies cleanly.
- Reason through the intended behavior AND design and confirm both are met; if you can't verify something, say so. For tenancy/security findings, explicitly confirm scoping still holds (agent can't read another agent's clients; client can't read another client's data). For fiscal findings, confirm the document is Arabic + carries the QR/stamp.

## Update the docs (same commit)
- In `COMPLETENESS_REVIEW.md`: mark the finding done (✅ + commit SHA) so the next session skips it.
- Add a traceability note mapping the SRS ID → the test you added.

## Commit (standalone repo)
- Stage code + test + doc; `git status` first; branch first if on the default branch.
- Message: `fix(<area>): <id> — <short description> [<finding id>]`; body = what changed, test added, acceptance + design states met. End with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Don't push unless asked; don't `--no-verify`. Fix hook failures at the cause.

## Stop and hand off
After committing, STOP. Print: finding done + SHA; intended-behavior + design status (met / unverified); any adjacent issue; the next-highest-severity unfixed finding ID. Then tell the operator verbatim:
> ✅ Committed. Run `/clear`, then start a new session with Prompt 3 (optionally `Finding: <next id>`) to continue in a clean context.

Do not begin the next finding in this session.
````
