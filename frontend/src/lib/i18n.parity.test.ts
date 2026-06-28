import { describe, it, expect } from 'vitest';
import { translations, type Language } from './i18n';

/**
 * Key-parity guard (ISSUE-196). English is the source of truth: every key in
 * `en` must exist in every other locale, or a non-English user hits an English
 * fallback / bare key in the UI. This mirrors the build-time gate in
 * `scripts/check-i18n-parity.mjs` so drift is caught in unit tests too.
 */
describe('i18n key parity', () => {
  const locales = Object.keys(translations) as Language[];
  const enKeys = Object.keys(translations.en);

  it('defines an en source-of-truth with no duplicate keys', () => {
    expect(enKeys.length).toBeGreaterThan(0);
    expect(new Set(enKeys).size).toBe(enKeys.length);
  });

  for (const lang of locales.filter((l) => l !== 'en')) {
    it(`'${lang}' is not short of 'en'`, () => {
      const missing = enKeys.filter((k) => !(k in translations[lang]));
      expect(missing, `'${lang}' missing: ${missing.join(', ')}`).toEqual([]);
    });

    it(`'${lang}' has no keys absent from 'en'`, () => {
      const extra = Object.keys(translations[lang]).filter((k) => !(k in translations.en));
      expect(extra, `'${lang}' extra: ${extra.join(', ')}`).toEqual([]);
    });
  }
});
