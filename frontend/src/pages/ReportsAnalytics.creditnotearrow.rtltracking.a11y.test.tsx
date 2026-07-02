import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The refund/void
// report links each credit note back to the invoice it refunds, rendered as
// `{credit_note} ← {original_invoice}`. The literal LEFTWARDS ARROW is a
// bidi-neutral glyph: the browser does NOT mirror it under `[dir="rtl"]`, so an
// Arabic/Urdu reader (who scans right-to-left) sees it point *away* from the
// original invoice. The dashboards' idiom for a mirrored horizontal arrow is
// Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180` too), and the glyph is
// decorative — both invoice numbers are already visible/announced — so it must
// also be `aria-hidden`.

const BASE = 'http://127.0.0.1:8000';

const REFUNDS_VOIDS = {
  days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  rows: [
    {
      type: 'refund',
      transaction_id: 1,
      invoice_number: 'CN-0007',
      actor_id: 'u1',
      actor: 'Alice',
      reason: 'Damaged item',
      amount: 42,
      timestamp: '2026-06-15T10:00:00Z',
      original_invoice: 'INV-0042',
    },
  ],
  refund_count: 1,
  refund_total: 42,
  void_count: 0,
  void_total: 0,
  csv_content: '',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ReportsAnalytics />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/refunds-voids`, () => HttpResponse.json(REFUNDS_VOIDS)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics credit-note back-reference arrow RTL mirroring (ISSUE-226)', () => {
  it('mirrors the credit-note → original-invoice arrow and hides it from SR', async () => {
    stubReports();
    renderPage();

    // The refund row renders its original invoice preceded by the back-arrow.
    await screen.findByText('INV-0042');
    const arrow = screen.getByText('←');
    expect(isMirrored(arrow)).toBe(true);
    // Decorative: both invoice numbers are already visible, so the glyph must
    // not be announced.
    expect(arrow.getAttribute('aria-hidden')).toBe('true');
  });
});
