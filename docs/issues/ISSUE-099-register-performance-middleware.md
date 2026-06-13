# ISSUE-099 — Register PerformanceMiddleware

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** U0.3 dead code · **Stories:** Further Notes

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`middlewares/production.py` defines `PerformanceMiddleware` but it is never registered, so `performance_monitor` stays empty. Register it (or delete it if perf monitoring isn't wanted). Prefer registering so the monitor populates.

## Acceptance criteria
- [ ] `PerformanceMiddleware` is registered on the app and `performance_monitor` populates on requests.
- [ ] Covered by a test asserting the monitor records a request.

## Blocked by
- None - can start immediately
