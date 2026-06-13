# ISSUE-029 — Webhook delivery logs: table + GET route + tab

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H24 · **Stories:** 31

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
WebhookManagement's "Delivery Logs" tab fetches `GET /production/webhooks/logs`, which doesn't exist (always 404, swallowed); dispatch outcomes are discarded. Add a `webhook_deliveries` table, persist each dispatch outcome, and a `GET /production/webhooks/logs` route the tab consumes (and a real "Deliveries Today" stat). Alternatively remove the tab + stat — but persisting is preferred for parity.

## Acceptance criteria
- [ ] A `webhook_deliveries` table records each dispatch (event, target, status, timestamp, response).
- [ ] `GET /production/webhooks/logs` returns persisted rows, owner-scoped.
- [ ] The Delivery Logs tab renders real rows; "Deliveries Today" is accurate.
- [ ] Covered by a test (fire event → row persisted → GET returns it).

## Blocked by
- ISSUE-020
