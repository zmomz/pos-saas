# ISSUE-097 — Remove UserProfile "Change Password managed by auth provider" block

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** atoms.dev residue · **Stories:** 58

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
UserProfile shows a "Change Password — managed by authentication provider" block left over from atoms.dev. Now that auth is local, remove the leftover block (and replace with a real change-password control if password-reset/complexity work warrants — otherwise just remove the misleading text).

## Acceptance criteria
- [ ] The misleading "managed by auth provider" block is removed.
- [ ] If a change-password control is added, it works against local auth; otherwise no dead control remains.
- [ ] Frontend builds/type-checks clean.

## Blocked by
- None - can start immediately
