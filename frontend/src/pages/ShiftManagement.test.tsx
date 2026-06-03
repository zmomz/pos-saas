import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// F-016 (POS-09): ShiftManagement read a response shape the endpoints never
// return — a flat `data.id` for the current shift (actually `{status, shift}`)
// and `data.items` for history (actually `{shifts, total}`), with snake_case
// money fields (`total_sales`/`cash_difference`) it never mapped. The bug: an
// open shift never showed as Active and the history money columns were blank.
// This test renders against the REAL endpoint shapes and asserts the page
// surfaces an active shift + populated history. It fails before the fix.

const BASE = 'http://127.0.0.1:8000/api/v1/production';

// The exact body `GET /shifts/current` returns for an OPEN shift.
const OPEN_CURRENT = {
  status: 'open',
  shift: {
    id: 42,
    start_time: '2026-06-03T08:00:00+00:00',
    opening_cash: 500,
    total_sales: 1234.5,
    total_transactions: 7,
    staff_name: 'Morning Cashier',
    branch_id: null,
    notes: null,
  },
};

// The exact body `GET /shifts/history` returns.
const HISTORY = {
  shifts: [
    {
      id: 41,
      staff_name: 'Cashier A',
      start_time: '2026-06-02T08:00:00+00:00',
      end_time: '2026-06-02T16:00:00+00:00',
      opening_cash: 100,
      closing_cash: 340,
      expected_cash: 335,
      cash_difference: 5,
      total_sales: 250,
      total_transactions: 12,
      branch_id: null,
      notes: null,
    },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <ShiftManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ShiftManagement reads the real shift endpoint shapes (F-016 / POS-09)', () => {
  it('renders an open shift as Active and populates history money columns', async () => {
    server.use(
      http.get(`${BASE}/shifts/current`, () => HttpResponse.json(OPEN_CURRENT)),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(HISTORY))
    );

    renderPage();

    // The open shift is unwrapped from `{status, shift}` → Active badge shows.
    expect(await screen.findByText('Active')).toBeInTheDocument();
    // ...and the current card maps `opening_cash`/`total_transactions`.
    expect(screen.getByText('SAR 500.00')).toBeInTheDocument();

    // History is read from `data.shifts` and snake_case fields are mapped:
    // staff, sales total (`total_sales`), and variance (`cash_difference`).
    expect(screen.getByText('Cashier A')).toBeInTheDocument();
    expect(screen.getByText('SAR 250.00')).toBeInTheDocument(); // sales_total
    expect(screen.getByText('+SAR 5.00')).toBeInTheDocument(); // cash_difference → difference
    expect(screen.queryByText('No shift history')).not.toBeInTheDocument();
  });

  it('renders the no-active-shift empty state for {status:no_open_shift, shift:null}', async () => {
    server.use(
      http.get(`${BASE}/shifts/current`, () =>
        HttpResponse.json({ status: 'no_open_shift', shift: null })
      ),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json({ shifts: [], total: 0 }))
    );

    renderPage();

    expect(await screen.findByText(/No active shift/i)).toBeInTheDocument();
    expect(screen.queryByText('Active')).not.toBeInTheDocument();
    expect(screen.getByText('No shift history')).toBeInTheDocument();
  });
});
