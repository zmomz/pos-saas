import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — one table voice. Every report panel that still
// renders a bespoke shadcn `<Table>` must speak the shared `.dxr-tbl` primitive
// (the same voice the payment-breakdown panel already uses). A migrated table
// carries the `dxr-tbl` class and is NOT wrapped in shadcn's `caption-bottom`
// `<table>` shell.

const BASE = 'http://127.0.0.1:8000';

const PNL = {
  days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  gross_sales: 1000,
  discounts: 100,
  net_revenue: 900,
  vat: 135,
  cogs: 400,
  gross_profit: 500,
  gross_margin_pct: 55.5,
  expenses: [{ category: 'Rent', amount: 200 }],
  total_expenses: 200,
  net_profit: 300,
  net_margin_pct: 33.3,
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

// Feed the P&L panel real data and null out every other report endpoint so the
// page renders without unhandled traffic.
function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/pnl`, () => HttpResponse.json(PNL)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics P&L shared table voice (ISSUE-208)', () => {
  it('renders the income statement through the shared .dxr-tbl primitive', async () => {
    stubReports();
    renderPage();

    // "Gross Sales" is unique to the income-statement table body.
    const cell = await screen.findByText('Gross Sales');
    const table = cell.closest('table') as HTMLElement;

    expect(table).toHaveClass('dxr-tbl');
    // shadcn's <Table> stamps `caption-bottom` on its <table>; the migrated
    // primitive must not.
    expect(table).not.toHaveClass('caption-bottom');
  });

  it('preserves the income-statement rows through the migration', async () => {
    stubReports();
    renderPage();

    const table = (await screen.findByText('Gross Sales')).closest('table') as HTMLElement;
    expect(within(table).getByText('Net Revenue')).toBeInTheDocument();
    expect(within(table).getByText('Gross Profit')).toBeInTheDocument();
    // The single operating-expense row survives.
    expect(within(table).getByText('Rent')).toBeInTheDocument();
  });

  it('leaves no bespoke shadcn <Table> in the rendered report', async () => {
    stubReports();
    renderPage();

    await screen.findByText('Gross Sales');
    // Every rendered table now speaks the shared voice; none carry shadcn's
    // `caption-bottom` shell class.
    const shadcnTables = document.querySelectorAll('table.caption-bottom');
    expect(shadcnTables.length).toBe(0);
  });
});
