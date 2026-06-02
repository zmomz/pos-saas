import { describe, it, expect } from 'vitest';
import {
  toArabicDigits,
  formatNumber,
  formatMoney,
  formatMoneyAr,
} from './format';

describe('format helpers (L10N-03)', () => {
  it('converts Western digits to Arabic-Indic', () => {
    expect(toArabicDigits('123')).toBe('١٢٣');
    expect(toArabicDigits(2026)).toBe('٢٠٢٦');
  });

  it('keeps Western digits for en, Arabic-Indic for ar/ur', () => {
    expect(formatNumber(1234.5, 'en')).toBe('1,234.50');
    expect(formatNumber(1234.5, 'ar')).toBe('١٬٢٣٤٫٥٠');
    expect(formatNumber(1234.5, 'ur')).toBe('١٬٢٣٤٫٥٠');
  });

  it('renders SAR currency (Western for en, ر.س for Arabic)', () => {
    expect(formatMoney(10, 'en')).toBe('10.00 SAR');
    expect(formatMoney(10, 'ar')).toContain('ر.س');
    expect(formatMoney(10, 'ar')).not.toContain('$');
  });

  it('formatMoneyAr always renders Arabic + ر.س', () => {
    const out = formatMoneyAr(99.5);
    expect(out).toContain('ر.س');
    expect(out).toMatch(/[٠-٩]/);
  });
});
