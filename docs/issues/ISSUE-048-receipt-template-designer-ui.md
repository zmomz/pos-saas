# ISSUE-048 — Receipt-template designer UI

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H26 · **Stories:** 47

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
With template fields now reaching the renderer (ISSUE-045), add a designer UI so a merchant can edit the template knobs (header/footer/logo/show_qr/font_size, width) with a live preview. Brand tokens, i18n/RTL, loading/empty/error states.

## Acceptance criteria
- [ ] A merchant can edit and save template fields with a preview reflecting changes.
- [ ] Saved template drives actual printed output.
- [ ] i18n/RTL-complete, brand tokens.
- [ ] Covered by a test (edit → save → render reflects).

## Blocked by
- ISSUE-045
