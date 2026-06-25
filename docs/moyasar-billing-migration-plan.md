# Moyasar Billing Migration — Scope & Plan

Replace Stripe entirely with Moyasar across two **independent** payment rails, and
align the data model + dashboards with the **wholesale-quota** business model
(not the previous revenue-share model). All Stripe code, Stripe-shaped comments,
and the now-meaningless revenue-share machinery are **removed**, not left dormant.

## Business model (authoritative)

```
Platform  --sells fixed-price quota (N client slots)-->  Agent
   ^  (Rail 1: Agent pays Platform — THIS is our revenue)
   |
Agent  --resells at his own price, collects himself-->  Merchant (Client)
          (Rail 2: Merchant pays Agent — the agent's money, not ours)
```

- **Rail 1 (NEW):** Agent buys/renews a quota → charged through the **platform's**
  Moyasar account (`MOYASAR_API_KEY`). This is the only revenue that is "ours".
- **Rail 2 (REWORK of the old Stripe path):** Merchant pays subscription → charged
  through **the agent's own** Moyasar account (per-agent keys stored on the agent).
  The platform hosts the UI but the money is the agent's.

Confirmed policy decisions:
1. **Cascade:** an agent who fails to pay us (Rail 1) is suspended, and his
   merchants are blocked at auth too (his whole quota goes dark).
2. **Commission ledger is dropped.** We don't skim merchant payments, so
   `commission_ledger` / `compute_commission_split` / `master_cut` / `agent_net`
   are removed. Agent revenue = raw sum of his merchant `subscription_payments`.
   Platform revenue = sum of `agent_quota_payments` (Rail 1).

## Card-on-file (both rails, via moyasar.js)

PAN never reaches the server (PAY-09). The browser tokenizes the card with
moyasar.js and posts back only a reusable token, stored **encrypted at rest**
(AES-256-GCM via `core/crypto.py`). Recurring charges reuse the stored token.
When no Moyasar key is configured the existing `SandboxGateway` path runs so the
flow stays demonstrable without credentials (OPS-08 parity).

---

## Data model changes

### `agents` (`models/agents.py`)
- **drop** `stripe_account_id`
- **add** (Rail 2 — the agent's own Moyasar account, encrypted):
  `moyasar_secret_key_enc`, `moyasar_publishable_key`, `moyasar_webhook_secret_enc`
- **add** (Rail 1 — the agent's card-on-file to pay us):
  `quota_card_token_enc`, `quota_card_last4`, `quota_card_brand`
- **add** (Rail 1 — the agent's quota subscription lifecycle):
  `quota_price` (Float), `quota_cycle` ('monthly'|'yearly'),
  `quota_status` ('active'|'past_due'|'dunning'|'suspended'),
  `quota_dunning_attempts` (Int), `quota_grace_deadline`, `next_quota_billing_date`

### `clients` (`models/clients.py`)
- **add** (Rail 2 — merchant card-on-file, charged via the agent's account):
  `moyasar_card_token_enc`, `card_last4`, `card_brand`

### NEW `agent_quota_payments` (`models/agent_quota_payments.py`)
Mirror of `subscription_payments` at agent grain (Rail 1 history):
`id, agent_id, user_id, amount, billing_cycle, period_start, period_end,
method, reference, note, created_at, updated_at`.

### REMOVED
- `models/commission_ledger.py`, `services/commission.py`, the
  `commission_ledger` table (Alembic drop).
- `services/payment.py` (orphan Stripe Checkout — no router imports it).
- `stripe` from `requirements.txt`.

### Migration
One Alembic revision: add new columns + `agent_quota_payments`, drop
`stripe_account_id` + `commission_ledger`. Existing agents backfill
`quota_status='active'` (grandfathered; first renewal will require a card).

---

## Backend work

### `core/crypto.py` (NEW)
Move the AES-256-GCM `encrypt_secret`/`decrypt_secret` here (key from
`SECRETS_ENCRYPTION_KEY` → `ZATCA_ENCRYPTION_KEY` → `JWT_SECRET_KEY`).
`services/zatca.py` re-exports from here (no behavior change, no duplicate impl).

### Rail 1 — `services/quota_billing.py` (NEW)
- `charge_quota(agent, *, idempotency_key)` → `MoyasarGateway(settings.moyasar_api_key)`
  + agent's stored quota card token; approved → `QuotaChargeResult`, declined →
  `QuotaChargeError`.
- `record_quota_payment(db, agent, charge, period...)` → writes `agent_quota_payments`,
  advances `next_quota_billing_date`, sets `quota_status='active'`, clears dunning.
- Reuse `services.dunning.next_dunning_state` (pure) for the agent's own dunning;
  `run_agent_quota_dunning` / `run_global_quota_dunning` mirror the merchant sweep.
- Suspend cascade: on `quota_status='suspended'`, set the agent `is_active=False`
  (auth block) — merchant auth already checks the owning agent.

### Rail 2 — rewrite `services/subscription_billing.py`
- `charge_subscription(agent, merchant, ...)`: resolve
  `MoyasarGateway(decrypt(agent.moyasar_secret_key_enc))` (**the agent's** account)
  + merchant's stored card token. No agent key OR no merchant card → raise
  `SubscriptionChargeError` (→ 402; **no silent "manual=free"**).
- `record_settled_payment`: drop the `commission_ledger` write + `compute_commission_split`.
  Just persist `subscription_payments`, advance billing, clear dunning.
- `ChargeResult.method` becomes `"moyasar"`; keep dataclass shape.

### `services/dunning.py`
- Drop `agent_stripe_account`; load the agent + merchant card; otherwise unchanged
  (state machine, notices, scheduler). Fix the stale "Stripe idempotency key" comment.

### `services/billing_scheduler.py`
- Run **both** sweeps per tick: `run_global_dunning` (Rail 2) and
  `run_global_quota_dunning` (Rail 1).

### `routers/tenant.py`
- **`create_agent` / `add_agent_slots`**: gate the slot grant on Rail 1 —
  attempt `charge_quota` (when the agent has a card / when master marks it paid).
  Quota price comes from the package `wholesale_price` (or explicit). Master may
  still provision with `quota_status='active'` for off-card/manual deals.
- **`pay_client_subscription`**: pass the agent + merchant card; remove
  `agent_stripe_account`. Keep coupon/trial logic.
- **`get_agent_revenue`**: rewrite to sum `subscription_payments` (no split).
  `RevenueByClient` loses `master_owed`/`net` → `collected`, `payments`.
- **`get_agent_commission_statements`**: rename concept to payment statements,
  sum `subscription_payments` per period (no split). (Route kept for the UI;
  response loses the split fields.)
- **`get_master_economics`**: `platform_revenue` = sum of `agent_quota_payments`.
  Merchant `collected` shown as agent GMV (informational). Leaderboard
  (`AgentEconomics`) loses `master_owed`/`net`; gains `quota_paid`.
- **Webhooks**: replace the single Stripe `/billing/webhook` with:
  - `POST /tenant/quota/webhook` — platform Moyasar (Rail 1), one secret, drives
    agent quota suspend/recover.
  - `POST /tenant/billing/webhook/agent/{agent_id}` — the agent's Moyasar (Rail 2),
    verified with that agent's stored webhook secret, drives merchant suspend/recover.
- **New endpoints**:
  - `POST /tenant/agent/quota/card` — agent saves their card (moyasar.js token).
  - `POST /tenant/agent/quota/pay` — agent buys/renews quota.
  - `GET  /tenant/agent/quota` — quota status + payment history.
  - `PUT  /tenant/agent/moyasar` — agent saves/validates their own Moyasar keys.
  - `POST /tenant/client/subscription/card` — merchant saves their card.

### Removals (no leftovers)
Delete `services/payment.py`, `services/commission.py`, `models/commission_ledger.py`;
strip every `stripe`/`master_cut`/`agent_net`/`commission` reference and comment in
`tenant.py`, `dunning.py`, `subscription_billing.py`, `pdf_render.py`
(`"stripe"` label → `"moyasar"`), `models/subscription_payments.py` comment,
and `requirements.txt`.

---

## Frontend work (`frontend/src`)

- **`lib/api.ts`**: remove nothing Stripe-named (none exposed); add
  `saveQuotaCard`, `payQuota`, `getQuotaStatus`, `saveAgentMoyasarKeys`,
  `saveSubscriptionCard`. Update `AgentRevenue`/economics types (drop split fields).
- **`lib/moyasar.ts` (NEW)**: thin moyasar.js loader + `tokenizeCard()`; sandbox
  token fallback when no publishable key (parity with backend sandbox).
- **AgentDashboard**: "Your quota" panel (status, next bill, pay/renew, card-on-file)
  + "Connect your Moyasar account" settings (keys) for collecting from merchants.
- **ClientDashboard**: merchant card-on-file panel; gate the Pay button on a saved card.
- **MasterDashboard**: economics panel reads `platform_revenue` (quota) + agent GMV;
  drop master_owed/net columns.
- **i18n** (`lib/i18n.ts`): new keys (en + ar complete; hi/ur fall back).

---

## Tests
- Keep `next_dunning_state` tests (pure; now exercised by both rails).
- Replace Stripe-mocked billing tests with Moyasar token charge approve/decline
  (both accounts), agent-key validation, both webhooks, "no card/no key → 402",
  quota-purchase-gates-provisioning, cascade-suspend.
- Delete commission-split tests; replace agent-revenue/economics tests with the
  payment-sum versions.

## Rollout / env
- `MOYASAR_API_KEY` (platform, Rail 1) + `MOYASAR_PUBLISHABLE_KEY` (frontend token).
- Per-agent keys entered in the agent settings UI (stored encrypted).
- `SECRETS_ENCRYPTION_KEY` recommended in production.
- Without any key: sandbox path keeps both rails demonstrable; **no silent free
  billing** — a real merchant charge with no agent key returns 402.

## Effort
~5–8 days: Rail 1 net-new (~2–3d), Rail 2 rework + per-agent keys/webhooks
(~2–3d), two card-on-file UIs (~2d), commission removal + dashboard rewrites +
tests (~1–2d). Merchant-facing POS untouched.
