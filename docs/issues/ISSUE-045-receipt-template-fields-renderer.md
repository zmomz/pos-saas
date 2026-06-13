# ISSUE-045 — Wire receipt-template fields into the renderer

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H26 · **Stories:** 47

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The renderer (`escpos.py`) never loads a template — labels are hardcoded, QR always emitted, no logo/header/font path — so all 11 template knobs are ignored at print time. Load the merchant's default template into `build_receipt`/`build_kot` and honor at minimum header/footer/logo/show_qr/font_size.

## Acceptance criteria
- [ ] `build_receipt`/`build_kot` load the default template and apply header/footer/logo/show_qr/font_size.
- [ ] Changing a template field changes the rendered output.
- [ ] Fiscal/kitchen printables still render in Arabic regardless of UI language.
- [ ] Covered by a test asserting template fields reach the rendered output.

## Blocked by
- None - can start immediately
