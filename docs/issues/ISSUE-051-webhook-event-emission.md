# ISSUE-051 — Fire all advertised webhook events (+ reconcile names)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H25 · **Stories:** 49

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The UI offers 9 events but `fire_event_background` runs only for `sale.completed` and `refund.created`; subscribers to shift/product/customer/inventory events never receive deliveries, and the backend `refund.created` vs UI `sale.refunded` names mismatch. Fire the remaining events at their source, and reconcile the event-name set so UI and backend agree (or trim `AVAILABLE_EVENTS` to what is actually emitted).

## Acceptance criteria
- [ ] Every event listed in the UI is fired at its source (or removed from the list).
- [ ] The refund event name is consistent across backend and UI.
- [ ] Deliveries persist (via ISSUE-029) and appear in logs.
- [ ] Covered by a test per emitted event.

## Blocked by
- ISSUE-029
