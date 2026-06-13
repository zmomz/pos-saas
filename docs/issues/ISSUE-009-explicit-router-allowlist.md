# ISSUE-009 — Replace blanket router discovery with an explicit allowlist

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** systemic (theme #1) · **Stories:** 8

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`include_routers_from_package(app, "routers")` auto-registers every `routers/*.py` exposing `router`/`admin_router`, which is how the orphaned scaffolds shipped live. Replace blanket discovery with explicit registration (or a discovery pass that consults a maintained, reviewed allowlist) so a newly-generated router cannot auto-ship on the API without a conscious decision.

## Acceptance criteria
- [ ] App boots mounting only the routers explicitly listed/allowed; the mounted-route set is unchanged versus post-purge state.
- [ ] Adding a new `routers/*.py` with no allowlist entry does NOT mount it.
- [ ] A test asserts the mounted router set matches the explicit list.

## Blocked by
- ISSUE-001 … ISSUE-008 (deletions must land first so the final list is correct)
