# ISSUE-019 — Append-only / tamper-evident audit log

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** P0 Audit · **Stories:** 22

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
With write/delete endpoints removed (ISSUE-006), make the audit store itself append-only and tamper-evident so the compliance trail can be trusted — e.g. a per-row hash chain (each row references the prior row's hash) and no application path that updates/deletes existing rows.

## Acceptance criteria
- [ ] Audit rows are write-once; no application code updates or deletes them.
- [ ] Each row carries a chaining hash linking it to the prior row; a tampered/removed row is detectable by verification.
- [ ] A test inserts rows, verifies the chain, then asserts mutation breaks verification.

## Blocked by
- ISSUE-006
