// ISSUE-238 — institutionalize the deep-review 7-sweep as a pre-merge
// regression gate. These guards assert the *infrastructure* exists so the
// honesty / i18n / contrast regressions the deep review found cannot quietly
// reappear: (1) a documented 7-sweep checklist, (2) a PR template that pulls
// each sweep into every PR, and (3) the i18n key-parity sweep wired into CI.
//
// The seven sweeps are the issue's canonical set (slugs are the contract the
// checklist + PR template must both carry): fabricated-state, swallowed-errors,
// i18n-key-parity, contrast, height-touch, table-voice, currency-date.
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '../../..');
const CHECKLIST = path.join(REPO_ROOT, '.github/REGRESSION_CHECKLIST.md');
const PR_TEMPLATE = path.join(REPO_ROOT, '.github/pull_request_template.md');
const CI = path.join(REPO_ROOT, '.github/workflows/ci.yml');

/** The canonical seven sweep slugs, in deep-review order. */
const SWEEPS = [
  'fabricated-state',
  'swallowed-errors',
  'i18n-key-parity',
  'contrast',
  'height-touch',
  'table-voice',
  'currency-date',
] as const;

const read = (p: string) => readFileSync(p, 'utf8');

describe('ISSUE-238 regression-checklist gate', () => {
  describe('a documented 7-sweep checklist exists', () => {
    it('the checklist file is present', () => {
      expect(existsSync(CHECKLIST)).toBe(true);
    });

    it('names all seven sweeps', () => {
      const body = read(CHECKLIST);
      const missing = SWEEPS.filter((s) => !body.includes(s));
      expect(missing, `checklist missing sweep slug(s): ${missing.join(', ')}`).toEqual([]);
    });
  });

  describe('the PR template references the checklist', () => {
    it('the PR template file is present', () => {
      expect(existsSync(PR_TEMPLATE)).toBe(true);
    });

    it('links to the regression checklist', () => {
      expect(read(PR_TEMPLATE)).toContain('REGRESSION_CHECKLIST.md');
    });

    it('surfaces every sweep as its own checkable item', () => {
      const body = read(PR_TEMPLATE);
      const missing = SWEEPS.filter((s) => !body.includes(s));
      expect(missing, `PR template missing sweep slug(s): ${missing.join(', ')}`).toEqual([]);
    });
  });

  describe('the i18n key-parity sweep is enforced in CI', () => {
    it('runs the parity gate as an explicit CI step', () => {
      const ci = read(CI);
      // The gate must be invoked by name so it is enforced (and visible) even
      // if the build step is ever reordered or replaced.
      expect(ci).toMatch(/i18n:check|check-i18n-parity/);
    });
  });
});
