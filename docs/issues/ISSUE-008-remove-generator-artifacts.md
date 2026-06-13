# ISSUE-008 — Remove dead generator artifacts

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** §4 dead code · **Stories:** 9

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove residual generator artifacts that advertise surface that isn't real: the `data_models/*.json` files with no runtime use (permissions, clients, client_features, categories, products, webhooks — only those whose routers are deleted/unused), and tidy the pervasive `…ss` double-plural naming and copy-paste docstrings across remaining generated routers/services. Scope this to dead/unused artifacts only — do not touch live entity triads still on the allowlist.

## Acceptance criteria
- [ ] Orphaned `data_models/*.json` files with no runtime reference are deleted.
- [ ] Copy-paste docstrings and `…ss` typos in touched modules are corrected (no behavior change).
- [ ] Full backend test suite green; no import breakage.

## Blocked by
- ISSUE-001, ISSUE-002, ISSUE-003, ISSUE-004 (their `data_models` json go with them)
