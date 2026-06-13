# ISSUE-049 — Devices settings page (register/list terminals)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H16 · **Stories:** 48

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The integrated SoftPOS terminal backend is complete (models, `GeideaTerminalGateway`, `/payments/terminals` + `/terminal/charge`) and `api.ts` clients exist (`registerTerminal`/`listTerminals`/`chargeTerminal`) with zero callers. Add a Devices settings page to register and list terminals for the merchant.

## Acceptance criteria
- [ ] A merchant can register a terminal and see the list of their terminals.
- [ ] Page is owner-scoped (uses the tenancy fix from ISSUE-011), brand tokens, i18n/RTL.
- [ ] Covered by a test (register → list shows it).

## Blocked by
- ISSUE-011
