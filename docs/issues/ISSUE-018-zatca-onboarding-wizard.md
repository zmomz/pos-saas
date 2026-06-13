# ISSUE-018 — ZATCA: in-app onboarding wizard (CSR → OTP → production CSID)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** P0 ZATCA · **Stories:** 20

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
A merchant currently cannot provision ZATCA credentials without raw API calls. Add an in-app onboarding wizard that walks CSR generation → OTP entry → production CSID issuance through the existing credential model, persisting the resulting per-client credentials. Renders loading/empty/error/permission states, brand tokens, full i18n/RTL.

## Acceptance criteria
- [ ] A merchant can complete CSR → OTP → production CSID in-app; credentials persist against their client.
- [ ] Errors at each step surface clearly (no swallowed failures).
- [ ] Wizard is i18n/RTL-complete and uses brand tokens.
- [ ] Backend endpoints round-trip the onboarding steps; covered by a test.

## Blocked by
- None - can start immediately
