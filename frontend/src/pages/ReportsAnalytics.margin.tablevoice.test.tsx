import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — one table voice. The Profit / COGS / Margin
// panel (RPT-04 / F-068) is the next holdout still rendering bespoke shadcn
// `<Table>`s. Its by-item, by-category and dead-stock tables must speak the
// shared `.dxr-tbl` primitive, the same voice the payment-breakdown, P&L,
// cash-flow and journal panels already use.

const BASE = 'http://127.0.0.1:8000';

const MARGIN = {
  days: 30,
  dead_stock_days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  by_item: [
    {
      key: 'p1',
      name: 'Espresso Beans',
      category: 'Coffee',
      qty_sold: 40,
      revenue: 1000,
      cogs: 400,
      gross_profit: 600,
      margin_pct: 60,
    },
  ],
  by_category: [
    {
      key: 'c1',
      name: 'Coffee',
      category: 'Coffee',
      qty_sold: 40,
      revenue: 1000,
      cogs: 400,
      gross_profit: 600,
      margin_pct: 60,
    },
  ],
  dead_stock: [
    {
      product_id: 7,
      name: 'Stale Mugs',
      category: 'Merch',
      quantity: 12,
      cost_price: 5,
      stock_value: 60,
    },
  ],
  totals: {
    key: 'total',
    name: 'Total',
    category: null,
    qty_sold: 40,
    revenue: 1000,
    cogs: 400,
    gross_profit: 600,
    margin_pct: 60,
  },
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

// Feed the margin panel real data and null out every other report endpoint so
// the page renders without unhandled traffic and no other table competes.
function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/profit-margin`, () => HttpResponse.json(MARGIN)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics Margin shared table voice (ISSUE-208)', () => {
  it('renders the by-item margin table through the shared .dxr-tbl primitive', async () => {
    stubReports();
    renderPage();

    const cell = await screen.findByText('Espresso Beans');
    const table = cell.closest('table') as HTMLElement;

    expect(table).toHaveClass('dxr-tbl');
    // shadcn's <Table> stamps `caption-bottom` on its <table>; the migrated
    // primitive must not.
    expect(table).not.toHaveClass('caption-bottom');
  });

  it('preserves the by-item, by-category and dead-stock rows', async () => {
    stubReports();
    renderPage();

    await screen.findByText('Espresso Beans');
    // by_category row.
    expect(screen.getByText('Coffee')).toBeInTheDocument();
    // dead_stock row.
    expect(screen.getByText('Stale Mugs')).toBeInTheDocument();
  });

  it('leaves no bespoke shadcn <Table> in the rendered margin report', async () => {
    stubReports();
    renderPage();

    await screen.findByText('Espresso Beans');
    const shadcnTables = document.querySelectorAll('table.caption-bottom');
    expect(shadcnTables.length).toBe(0);
  });
});
