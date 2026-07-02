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

// The headline KPIs are the one hard dependency; everything else degrades to
// null on failure, so we only stub the dashboard endpoint and let the rest of
// the hybrid fan-out (branding/transactions/retail/restaurant focus) fall
// through and be swallowed by their own .catch handlers.
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ClientDashboard sale-mode switch announces its selection (ISSUE-226)', () => {
  it('exposes the selected sale mode via aria-pressed, not colour alone', async () => {
    server.use(
      http.get(`${BASE}/tenant/client/dashboard`, () =>
        HttpResponse.json({ today_sales: 0, today_transactions: 0, total_products: 0, low_stock_count: 0 })
      )
    );

    renderPage();

    // The active segment (default 'retail') is announced as pressed…
    const retail = await screen.findByRole('button', { name: 'Retail', pressed: true });
    expect(retail).toBeInTheDocument();

    // …and the other segments announce their un-pressed state.
    expect(screen.getByRole('button', { name: 'Table', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Takeaway', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delivery', pressed: false })).toBeInTheDocument();
  });
});
