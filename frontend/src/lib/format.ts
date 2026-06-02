/**
 * Locale-aware number/currency formatting (SRS L10N-03).
 *
 * Arabic and Urdu render with Arabic-Indic numerals (٠١٢٣٤٥٦٧٨٩) and the Arabic
 * decimal/thousands separators; other languages keep Western digits. The
 * always-Arabic fiscal documents (receipt / invoice / quotation) call the
 * `*Ar` helpers directly so they read natively in Arabic regardless of the UI
 * language the cashier picked.
 */
import type { Language } from './i18n';

const WESTERN_TO_ARABIC: Record<string, string> = {
  '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
  '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩',
};

const ARABIC_DECIMAL = '٫';
const ARABIC_THOUSANDS = '٬';

/** Replace every Western digit with its Arabic-Indic equivalent. */
export function toArabicDigits(input: string | number): string {
  return String(input).replace(/[0-9]/g, (d) => WESTERN_TO_ARABIC[d]);
}

function usesArabicDigits(lang: Language): boolean {
  return lang === 'ar' || lang === 'ur';
}

/** Format a number for the given language (Arabic-Indic digits for ar/ur). */
export function formatNumber(value: number, lang: Language, decimals = 2): string {
  const western = value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (!usesArabicDigits(lang)) return western;
  return western
    .replace(/,/g, ARABIC_THOUSANDS)
    .replace(/\./g, ARABIC_DECIMAL)
    .replace(/[0-9]/g, (d) => WESTERN_TO_ARABIC[d]);
}

/** Always render a number in Arabic-Indic form (for always-Arabic documents). */
export function formatNumberAr(value: number, decimals = 2): string {
  return formatNumber(value, 'ar', decimals);
}

/** Currency string. SAR-only system; symbol is the Arabic ﷼ abbreviation ر.س. */
export function formatMoney(value: number, lang: Language, decimals = 2): string {
  return `${formatNumber(value, lang, decimals)} ${lang && !usesArabicDigits(lang) ? 'SAR' : 'ر.س'}`;
}

/** Always render money in Arabic (for the always-Arabic receipt/invoice). */
export function formatMoneyAr(value: number, decimals = 2): string {
  return `${formatNumberAr(value, decimals)} ر.س`;
}

/**
 * Locale-aware date formatting (SRS L10N-04). Gregorian is the required
 * calendar; Arabic/Urdu render Arabic-Indic digits. Pass `{ hijri: true }` to
 * additionally append the Umm al-Qura (Islamic) date in parentheses.
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
  // Force Gregorian even for ar-SA (which defaults to Islamic) via the -u-ca-gregory extension.
  let out = new Intl.DateTimeFormat(`${LOCALE_BY_LANG[lang]}-u-ca-gregory`, dateOpts).format(date);

  if (opts.hijri) {
    const hijri = new Intl.DateTimeFormat('ar-SA-u-ca-islamic-umalqura', {
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
