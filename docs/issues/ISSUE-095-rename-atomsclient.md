# ISSUE-095 — Rename `atomsClient.ts`→`apiClient.ts` + drop SDK shims

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** atoms.dev residue · **Stories:** 58

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Rename the migration-cruft `atomsClient.ts` to `apiClient.ts` and remove the unused SDK-shim methods `auth.me`/`auth.login`/`auth.toLogin`. Update all imports. (Do this after the 401-interceptor work in ISSUE-041/042 so the rename doesn't collide with active edits.)

## Acceptance criteria
- [ ] File renamed to `apiClient.ts`; all imports updated.
- [ ] `auth.me`/`auth.login`/`auth.toLogin` shims removed (no callers).
- [ ] Frontend builds/type-checks clean.

## Blocked by
- ISSUE-041, ISSUE-042
