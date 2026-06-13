# ISSUE-020 — Stop swallowing errors on façade pages

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** C4/H24/H27 precondition · **Stories:** 29

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
LoyaltyProgram, WebhookManagement (delivery logs), and the storage callers wrap missing-endpoint calls in swallowing try/catch, so 404/500 render as empty/inert panels and the façades silently "work." Remove (or surface) those catches so a missing endpoint becomes a visible error. This is the do-first prerequisite that makes ISSUE-028/029/030 diagnosable.

## Acceptance criteria
- [ ] Swallowing catches on the loyalty, webhook-logs, and storage call sites are removed or converted to a surfaced error state.
- [ ] A missing/failing endpoint now renders an error (toast/error panel), not a silent empty view.
- [ ] No new uncaught runtime crash on the affected pages.

## Blocked by
- None - can start immediately
