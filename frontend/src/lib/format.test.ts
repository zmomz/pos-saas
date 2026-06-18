import { describe, it, expect } from 'vitest';
import {
  toArabicDigits,
  formatNumber,
  formatMoney,
  formatMoneyAr,
} from './format';

describe('format helpers (L10N-03)', () => {
  it('toArabicDigits is now a Western-digit pass-through', () => {
    expect(toArabicDigits('123')).toBe('123');
    expect(toArabicDigits(2026)).toBe('2026');
  });

  it('uses Western numerals + separators for every language', () => {
    expect(formatNumber(1234.5, 'en')).toBe('1,234.50');
    expect(formatNumber(1234.5, 'ar')).toBe('1,234.50');
    expect(formatNumber(1234.5, 'ur')).toBe('1,234.50');
  });

  it('renders the Saudi Riyal symbol (U+20C1) in every language', () => {
    expect(formatMoney(10, 'en')).toBe('10.00 ⃁');
    expect(formatMoney(10, 'ar')).toBe('10.00 ⃁');
    // Western digits only — never Arabic-Indic.
    expect(formatMoney(10, 'ar')).not.toMatch(/[٠-٩]/);
    // The symbol is the new SAR sign, not the old text labels.
    expect(formatMoney(10, 'en')).not.toMatch(/SAR|ر\.س/);
  });

  it('formatMoneyAr renders Western digits + the Riyal symbol', () => {
    const out = formatMoneyAr(99.5);
    expect(out).toBe('99.50 ⃁');
    expect(out).not.toMatch(/[٠-٩]/);
  });
});
