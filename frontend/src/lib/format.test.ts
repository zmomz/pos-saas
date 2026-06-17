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

  it('renders SAR currency (SAR for Latin, ر.س label for Arabic)', () => {
    expect(formatMoney(10, 'en')).toBe('10.00 SAR');
    expect(formatMoney(10, 'ar')).toBe('10.00 ر.س');
    expect(formatMoney(10, 'ar')).not.toMatch(/[٠-٩]/);
  });

  it('formatMoneyAr renders Western digits + the ر.س label', () => {
    const out = formatMoneyAr(99.5);
    expect(out).toBe('99.50 ر.س');
    expect(out).not.toMatch(/[٠-٩]/);
  });
});
