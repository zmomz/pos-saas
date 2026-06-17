/**
 * Locale-aware number/currency formatting (SRS L10N-03).
 *
 * Numbers render with Western numerals (1234567890) and Western
 * thousands/decimal separators in EVERY language — including Arabic and the
 * always-Arabic fiscal documents. (Per product decision 2026-06-18: Eastern
 * Arabic-Indic digits ٠١٢٣ are never shown unless an explicit user preference
 * asks for them.) Currency keeps the localized SAR label: `SAR` for Latin
 * languages, the Arabic abbreviation `ر.س` for Arabic/Urdu and the
 * always-Arabic documents.
 */
import type { Language } from './i18n';

function usesArabicLabel(lang: Language): boolean {
  return lang === 'ar' || lang === 'ur';
}

/**
 * Pass-through kept for backward compatibility. We no longer convert to
 * Arabic-Indic digits anywhere; this now returns the value as a Western-digit
 * string. Prefer using the raw value directly.
 */
export function toArabicDigits(input: string | number): string {
  return String(input);
}

/** Format a number with Western numerals and separators for every language. */
export function formatNumber(value: number, _lang: Language, decimals = 2): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Western-numeral number (kept for the always-Arabic fiscal documents). */
export function formatNumberAr(value: number, decimals = 2): string {
  return formatNumber(value, 'ar', decimals);
}

/** SAR currency label only — ر.س in RTL languages, SAR otherwise. */
export function currencyLabel(lang: Language): string {
  return usesArabicLabel(lang) ? 'ر.س' : 'SAR';
}

/** Currency string. SAR-only system; symbol is the Arabic ﷼ abbreviation ر.س. */
export function formatMoney(value: number, lang: Language, decimals = 2): string {
  return `${formatNumber(value, lang, decimals)} ${currencyLabel(lang)}`;
}

/** Money for the always-Arabic receipt/invoice: Western digits + ر.س label. */
export function formatMoneyAr(value: number, decimals = 2): string {
  return `${formatNumberAr(value, decimals)} ر.س`;
}

/**
 * Locale-aware date formatting (SRS L10N-04). Gregorian is the required
 * calendar and Western numerals are forced in every language via the
 * `-nu-latn` numbering-system extension (ar-SA otherwise emits Arabic-Indic
 * digits). Pass `{ hijri: true }` to additionally append the Umm al-Qura
 * (Islamic) date in parentheses.
 */
const LOCALE_BY_LANG: Record<Language, string> = {
  ar: 'ar-SA',
  en: 'en-GB',
  hi: 'hi-IN',
  ur: 'ur-PK',
};

function toDate(value: Date | string | number): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatDate(
  value: Date | string | number,
  lang: Language,
  opts: { hijri?: boolean; withTime?: boolean } = {}
): string {
  const date = toDate(value);
  if (isNaN(date.getTime())) return '';

  const dateOpts: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    calendar: 'gregory',
    ...(opts.withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  };
  // Force Gregorian + Western (Latin) numerals even for ar-SA, which otherwise
  // defaults to the Islamic calendar and Arabic-Indic digits.
  let out = new Intl.DateTimeFormat(`${LOCALE_BY_LANG[lang]}-u-ca-gregory-nu-latn`, dateOpts).format(date);

  if (opts.hijri) {
    const hijri = new Intl.DateTimeFormat('ar-SA-u-ca-islamic-umalqura-nu-latn', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date);
    out = `${out} (${hijri})`;
  }
  return out;
}

/** Date + time convenience (L10N-04). */
export function formatDateTime(
  value: Date | string | number,
  lang: Language,
  opts: { hijri?: boolean } = {}
): string {
  return formatDate(value, lang, { ...opts, withTime: true });
}
