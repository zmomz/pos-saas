# ISSUE-073 — KDS bumped-card / undo view

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 restaurant / U4.2 · **Stories:** 53

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The KDS recall button is gated on `status==='bumped'` but the board only holds active cards, so it never renders. Add a bumped-card view (recently completed) with an undo/recall action so a bumped ticket can be brought back.

## Acceptance criteria
- [ ] Bumped cards are viewable on a dedicated view/filter.
- [ ] A bumped card can be recalled back to active.
- [ ] Covered by a test (bump → appears in bumped view → recall restores).

## Blocked by
- None - can start immediately
