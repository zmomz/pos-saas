# ISSUE-096 — Remove the now-superseded dead `refreshAccessToken` residue

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** atoms.dev residue · **Stories:** 58

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
After ISSUE-041 wires `refreshAccessToken()` into the interceptor, remove any remaining dead/duplicate refresh-token scaffolding that is genuinely unused (NOT the now-wired function). This is a cleanup pass to ensure no orphaned duplicate remains.

## Acceptance criteria
- [ ] The live `refreshAccessToken()` used by the interceptor remains; any duplicate/dead copy is removed.
- [ ] No unused refresh-token helpers remain.
- [ ] Frontend builds/type-checks clean.

## Blocked by
- ISSUE-041
