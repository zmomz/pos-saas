# ISSUE-098 — Remove Chinese-comment storage scaffold + `settingsApi`/.env editor orphan

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** atoms.dev residue / U6.1 · **Stories:** 58

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Clean the remaining residue: the Chinese-comment storage scaffold (`统一的 OSS 服务请求方法` + wrong return annotation + copy-paste log strings) and the orphaned `frontend/src/api/settings.ts` (`settingsApi`, imported nowhere) / the allowlisted `.env`-editor `routers/settings.py` orphan. Resolve consistently with the storage decision in ISSUE-030.

## Acceptance criteria
- [ ] Dead storage residue (comments/annotations/log strings) cleaned or removed per the ISSUE-030 outcome.
- [ ] `settingsApi` and the `.env` settings editor orphan are removed (or wired if intentionally kept).
- [ ] Builds/type-checks clean; `tests/test_orphan_routers.py` updated if `settings.py` is removed.

## Blocked by
- ISSUE-030
