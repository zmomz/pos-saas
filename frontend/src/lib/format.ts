/**
 * Locale-aware number/currency formatting (SRS L10N-03).
 *
 * Numbers render with Western numerals (1234567890) and Western
 * thousands/decimal separators in EVERY language — including Arabic and the
 * always-Arabic fiscal documents. (Per product decision 2026-06-18: Eastern
 * Arabic-Indic digits ٠١٢٣ are never shown unless an explicit user preference
 * asks for them.)
 *
 * Currency uses the **official Saudi Riyal symbol** ﷼ (U+20C1) in every
 * language — a single, language-neutral mark like `$` or `€`, replacing the
 * older `SAR` / `ر.س` text labels (product decision 2026-06-18). The glyph is
 * supplied by the bundled `Saudi Riyal` webfont (scoped to U+20C1 via
 * `unicode-range`; see index.css), so it renders in plain strings everywhere.
 */
import type { Language } from './i18n';

/** Official Saudi Riyal sign (U+20C1). Use this everywhere instead of literals. */
export const RIYAL = '⃁';

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

/** Currency symbol — the Saudi Riyal sign (U+20C1) in every language. */
export function currencyLabel(_lang?: Language): string {
  return RIYAL;
}

/** Currency string. SAR-only system; the symbol is the Saudi Riyal sign ﷼. */
export function formatMoney(value: number, lang: Language, decimals = 2): string {
  return `${formatNumber(value, lang, decimals)} ${RIYAL}`;
}

/** Money for the always-Arabic receipt/invoice: Western digits + Riyal sign. */
export function formatMoneyAr(value: number, decimals = 2): string {
  return `${formatNumberAr(value, decimals)} ${RIYAL}`;
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

/** Time-only convenience (L10N-04): locale-aware HH:MM, Western numerals. */
export function formatTime(
  value: Date | string | number,
  lang: Language
): string {
  const date = toDate(value);
  if (isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(`${LOCALE_BY_LANG[lang]}-u-ca-gregory-nu-latn`, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** Date + time convenience (L10N-04). */
export function formatDateTime(
  value: Date | string | number,
  lang: Language,
  opts: { hijri?: boolean } = {}
): string {
  return formatDate(value, lang, { ...opts, withTime: true });
}
