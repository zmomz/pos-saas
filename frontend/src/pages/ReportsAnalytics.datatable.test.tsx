import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — the payment-breakdown panel must speak the one
// shared table voice: the `.dxr-tbl` primitive, not a bespoke shadcn `<Table>`.
// Column semantics (method, collected, refunds, net, txns) and the summary
// total row must survive the migration.

const BASE = 'http://127.0.0.1:8000';

const TENDERS = {
  tenders: [
    { tender_type: 'cash', collected: 1000, refunds: 0, net: 1000, count: 12 },
    { tender_type: 'mada', collected: 500, refunds: 50, net: 450, count: 7 },
  ],
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Every other report panel fetches on mount; stub the payment-breakdown panel
// with data and null out the rest so the page renders without unhandled traffic.
function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/payment-breakdown`, () => HttpResponse.json(TENDERS)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics payment breakdown shared table voice (ISSUE-208)', () => {
  it('renders the payment breakdown through the shared .dxr-tbl primitive', async () => {
    stubReports();

    renderPage();

    expect(await screen.findByText('Cash')).toBeInTheDocument();

    // "Cash" is unique to the payment-breakdown panel; its enclosing table must
    // now be the shared `.dxr-tbl`, not a bespoke shadcn `<Table>`.
    const table = screen.getByText('Cash').closest('table') as HTMLElement;
    expect(table).toHaveClass('dxr-tbl');
  });

  it('preserves the tender rows, netted refunds and the summary total', async () => {
    stubReports();

    renderPage();

    expect(await screen.findByText('Cash')).toBeInTheDocument();
    const table = (screen.getByText('Cash').closest('table')) as HTMLElement;
    expect(table).toHaveClass('dxr-tbl');

    // Both tenders survive the migration.
    expect(within(table).getByText('Mada')).toBeInTheDocument();
    // Refunds render as a signed, formatted delta ("- ⃁ 50.00"), not a bypass.
    expect(within(table).getByText(/- .*50/)).toBeInTheDocument();
    // The summary total row survives: nets sum to 1450.
    expect(within(table).getByText(/1,?450/)).toBeInTheDocument();
  });
});
