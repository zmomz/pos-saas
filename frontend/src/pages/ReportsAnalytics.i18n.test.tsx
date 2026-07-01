import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { translate } from '@/lib/i18n';

/**
 * ISSUE-208 (M11 FE-Platform): ReportsAnalytics' private 449-line locale map is
 * migrated into the shared `lib/i18n.ts` translation table, so report labels go
 * through the single `translate`/`useLanguage().t` path like the rest of the app.
 */
describe('ReportsAnalytics i18n migration', () => {
  it('report-specific keys resolve through the shared translate() in every locale', () => {
    expect(translate('en', 'reports_analytics')).toBe('Reports & Analytics');
    expect(translate('en', 'sales_chart')).toBe('Sales Overview');
    expect(translate('en', 'avg_order_value')).toBe('Average Order Value');
    expect(translate('en', 'payment_breakdown')).toBe('Payment Breakdown');

    // Non-English locales carry the migrated report strings (parity-guarded).
    expect(translate('ar', 'sales_chart')).toBe('نظرة عامة على المبيعات');
    expect(translate('ar', 'payment_breakdown')).toBe('تفصيل طرق الدفع');
  });

  it('no longer declares a private reportTranslations map', () => {
    const src = readFileSync(resolve('src/pages/ReportsAnalytics.tsx'), 'utf8');
    expect(src).not.toMatch(/const\s+reportTranslations\b/);
  });
});
