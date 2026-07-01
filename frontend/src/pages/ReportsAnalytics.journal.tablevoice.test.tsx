import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — one table voice. The Accounting Journal / GL
// export panel (FIN-02) is the next holdout still rendering a bespoke shadcn
// `<Table>`. Its double-entry lines + running debit/credit totals row must speak
// the shared `.dxr-tbl` primitive, the same voice the payment-breakdown, P&L and
// cash-flow panels already use.

const BASE = 'http://127.0.0.1:8000';

const JOURNAL = {
  days: 30,
  from_date: '2026-06-01',
  to_date: '2026-07-01',
  lines: [
    {
      account_code: '4000',
      account: 'Sales Revenue',
      description: 'Net sales for period',
      debit: 0,
      credit: 1000,
    },
    {
      account_code: '1000',
      account: 'Cash',
      description: 'Cash receipts',
      debit: 1000,
      credit: 0,
    },
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Feed the journal panel real data and null out every other report endpoint so
// the page renders without unhandled traffic and no other table competes.
function stubReports() {
  server.use(
    http.get(`${BASE}/api/v1/reports/journal-export`, () => HttpResponse.json(JOURNAL)),
    http.get(`${BASE}/api/v1/reports/*`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null))
  );
}

describe('ReportsAnalytics Journal shared table voice (ISSUE-208)', () => {
  it('renders the journal table through the shared .dxr-tbl primitive', async () => {
    stubReports();
    renderPage();

    // "Sales Revenue" is a unique GL-account row of the journal table.
    const cell = await screen.findByText('Sales Revenue');
    const table = cell.closest('table') as HTMLElement;

    expect(table).toHaveClass('dxr-tbl');
    // shadcn's <Table> stamps `caption-bottom` on its <table>; the migrated
    // primitive must not.
    expect(table).not.toHaveClass('caption-bottom');
  });

  it('preserves the journal lines and the running debit/credit totals row', async () => {
    stubReports();
    renderPage();

    const table = (await screen.findByText('Sales Revenue')).closest('table') as HTMLElement;
    // The second GL line and the balanced totals both survive the migration.
    expect(within(table).getByText('Cash')).toBeInTheDocument();
    // 1000 appears in credit (Sales), debit (Cash) and both totals cells.
    expect(within(table).getAllByText(/1,?000\.00/).length).toBeGreaterThanOrEqual(2);
  });

  it('leaves no bespoke shadcn <Table> in the rendered journal report', async () => {
    stubReports();
    renderPage();

    await screen.findByText('Sales Revenue');
    const shadcnTables = document.querySelectorAll('table.caption-bottom');
    expect(shadcnTables.length).toBe(0);
  });
});
