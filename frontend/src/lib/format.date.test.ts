import { describe, it, expect } from 'vitest';
import { formatDate, formatDateTime } from './format';

const SAMPLE = new Date('2026-06-03T14:30:00Z');

describe('locale-aware date helper (L10N-04)', () => {
  it('formats a Gregorian date for en', () => {
    const out = formatDate(SAMPLE, 'en');
    expect(out).toMatch(/2026/);
    // dd/mm/yyyy-ish for en-GB
    expect(out).toMatch(/0?3/);
  });

  it('uses Arabic-Indic digits for ar', () => {
    const out = formatDate(SAMPLE, 'ar');
    expect(out).toMatch(/[٠-٩]/);
  });

  it('appends a Hijri date when requested', () => {
    const out = formatDate(SAMPLE, 'en', { hijri: true });
    expect(out).toMatch(/\(.+\)/);
  });

  it('formatDateTime includes a time component', () => {
    const out = formatDateTime(SAMPLE, 'en');
    expect(out).toMatch(/\d{1,2}:\d{2}/);
  });

  it('returns empty string for an invalid date', () => {
    expect(formatDate('not-a-date', 'en')).toBe('');
  });
});
