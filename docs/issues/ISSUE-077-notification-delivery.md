# ISSUE-077 — Email/SMS/push notification delivery honoring prefs

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 settings · **Stories:** 55

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Notifications are configured but not delivered per user preference. Wire actual email/SMS/push delivery that honors each user's UserProfile notification preferences.

## Acceptance criteria
- [ ] Notifications dispatch via the configured channel(s) only when the user's prefs allow.
- [ ] Disabled channels are not sent.
- [ ] Covered by a test asserting delivery respects prefs.

## Blocked by
- ISSUE-078
