import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-226 (M11 FE-Platform · a11y) — the dashboard "Default sale mode"
// segmented control (a `both` merchant only) signalled its selected segment
// with a `data-active` attribute ALONE. `data-active` is a styling hook; it is
// invisible to assistive tech, so a screen-reader user tabbing the switch could
// not tell which sale mode was current. Route it through the shared `SegButton`
// primitive so the selection is announced via `aria-pressed` (WCAG 4.1.2).

const BASE = 'http://127.0.0.1:8000/api/v1';

// Only a hybrid (`both`) merchant gets the sale-mode switch, so force that type.
// The default sale mode is 'retail'.
vi.mock('@/contexts/BusinessProfileContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/contexts/BusinessProfileContext')>();
  return {
    ...actual,
    useBusinessProfile: () => ({
      businessType: 'both',
      profile: null,
      ready: true,
      refresh: async () => {},
      saleMode: 'retail',
      setSaleMode: () => {},
    }),
  };
});

import ClientDashboard from './ClientDashboard';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ClientDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

// The headline KPIs are the one hard dependency. The rest of the hybrid fan-out
// (branding/transactions/subscription block loading; retail+restaurant focus
// fire after) degrades to null on failure — but if we let those fall through to
// the real network (`bypass`), each request races a connection attempt whose
// latency balloons under full-suite parallel load, so `loadData` (which awaits
// the branding/transactions/subscription Promise.all before it clears the
// loading gate) could out-run the query's default 1s timeout and flake. Stub
// every endpoint the hybrid dashboard touches so the page settles deterministically
// with zero real-network I/O.
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Empty-but-valid stubs for the non-KPI fan-out. Each loader has its own .catch,
// so the exact shape is immaterial — only that the request resolves locally and
// immediately instead of reaching for 127.0.0.1:8000.
function stubDashboardFanout() {
  server.use(
    http.get(`${BASE}/tenant/client/dashboard`, () =>
      HttpResponse.json({ today_sales: 0, today_transactions: 0, total_products: 0, low_stock_count: 0 })
    ),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json({ company_name: '' })),
    http.get(`${BASE}/tenant/client/subscription`, () => HttpResponse.json(null)),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/products/low-stock`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/reports/top-products`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/reports/inventory`, () => HttpResponse.json({ total_valuation: 0 })),
    http.get(`${BASE}/restaurant/tables`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/restaurant/kds/tickets`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/restaurant/reservations`, () => HttpResponse.json({ items: [], total: 0 })),
  );
}

describe('ClientDashboard sale-mode switch announces its selection (ISSUE-226)', () => {
  it('exposes the selected sale mode via aria-pressed, not colour alone', async () => {
    stubDashboardFanout();

    renderPage();

    // The active segment (default 'retail') is announced as pressed…
    const retail = await screen.findByRole('button', { name: 'Retail', pressed: true }, { timeout: 3000 });
    expect(retail).toBeInTheDocument();

    // …and the other segments announce their un-pressed state.
    expect(screen.getByRole('button', { name: 'Table', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Takeaway', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delivery', pressed: false })).toBeInTheDocument();
  });
});
