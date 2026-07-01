import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The Accounting
// Journal panel prints its reporting window as `{from_date} → {to_date}`. The
// literal LEFTWARDS/RIGHTWARDS-arrow glyph is a bidi-neutral character: the
// browser does NOT mirror it under `[dir="rtl"]`, so an Arabic/Urdu reader (who
// scans right-to-left) sees the arrow point *away* from the destination date.
// The dashboards' idiom for a mirrored horizontal arrow is Tailwind's
// `rtl:-scale-x-100` (accept `rtl:rotate-180` too). The transition arrow must
// carry that class so it flips to point in the reading direction.

const BASE = 'http://127.0.0.1:8000';

const JOURNAL = {
  days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  lines: [
    { account_code: '4000', account: 'Sales Revenue', description: 'Net sales', debit: 0, credit: 1000 },
    { account_code: '1000', account: 'Cash', description: 'Cash receipts', debit: 1000, credit: 0 },
  ],
  total_debit: 1000,
  total_credit: 1000,
  balanced: true,
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
    http.get(`${BASE}/api/v1/reports/journal-export`, () => HttpResponse.json(JOURNAL)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics journal date-range arrow RTL mirroring (ISSUE-226)', () => {
  it('mirrors the transition arrow between the from/to dates under RTL', async () => {
    stubReports();
    renderPage();

    // The panel renders on load; the arrow lives between the two window dates.
    await screen.findByText('Sales Revenue');
    const arrow = screen.getByText('→');
    expect(isMirrored(arrow)).toBe(true);
    // The glyph is decorative — the dates already convey the range to a
    // screen reader, so the arrow must not be announced twice.
    expect(arrow.getAttribute('aria-hidden')).toBe('true');
  });
});
