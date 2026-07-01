import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — one table voice. The Cash Flow statement panel
// (operating cash flow + receipts-by-tender) is the next holdout still rendering
// bespoke shadcn `<Table>`s. Both must speak the shared `.dxr-tbl` primitive, the
// same voice the payment-breakdown and P&L panels already use.

const BASE = 'http://127.0.0.1:8000';

const CASH_FLOW = {
  days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  receipts_collected: 1200,
  receipts_refunds: 200,
  receipts_net: 1000,
  by_tender: [
    { tender_type: 'cash', collected: 700, refunds: 100, net: 600 },
    { tender_type: 'card', collected: 500, refunds: 100, net: 400 },
  ],
  expenses: [{ category: 'Rent', amount: 300 }],
  total_expenses: 300,
  inflows: [{ label: 'Sales Receipts', amount: 1000 }],
  outflows: [{ label: 'Operating Expenses', amount: 300 }],
  net_cash_flow: 700,
  drawer_movements: { pay_in: 50, pay_out: 20, cash_drop: 10, net_drawer: 20 },
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Feed the cash-flow panel real data and null out every other report endpoint so
// the page renders without unhandled traffic and no other table competes.
function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/cash-flow`, () => HttpResponse.json(CASH_FLOW)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics Cash Flow shared table voice (ISSUE-208)', () => {
  it('renders the operating cash-flow table through the shared .dxr-tbl primitive', async () => {
    stubReports();
    renderPage();

    // "Sales Receipts" is a unique inflow row of the operating cash-flow table.
    const cell = await screen.findByText('Sales Receipts');
    const table = cell.closest('table') as HTMLElement;

    expect(table).toHaveClass('dxr-tbl');
    // shadcn's <Table> stamps `caption-bottom` on its <table>; the migrated
    // primitive must not.
    expect(table).not.toHaveClass('caption-bottom');
  });

  it('preserves the operating cash-flow rows through the migration', async () => {
    stubReports();
    renderPage();

    const table = (await screen.findByText('Sales Receipts')).closest('table') as HTMLElement;
    // The outflow row and the running net summary both survive.
    expect(within(table).getByText('Operating Expenses')).toBeInTheDocument();
  });

  it('renders the receipts-by-tender table through the shared .dxr-tbl primitive', async () => {
    stubReports();
    renderPage();

    // The tender table's "Collected"/"Refunds"/"Net" headers plus two tender rows.
    await screen.findByText('Sales Receipts');
    const tables = Array.from(document.querySelectorAll('table.dxr-tbl'));
    // Both the operating cash-flow table and the receipts-by-tender table now
    // speak the shared voice.
    expect(tables.length).toBe(2);
  });

  it('leaves no bespoke shadcn <Table> in the rendered cash-flow report', async () => {
    stubReports();
    renderPage();

    await screen.findByText('Sales Receipts');
    const shadcnTables = document.querySelectorAll('table.caption-bottom');
    expect(shadcnTables.length).toBe(0);
  });
});
