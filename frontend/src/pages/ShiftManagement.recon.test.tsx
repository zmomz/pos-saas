import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// Issue #210 (M3·POS) — inventory reconciliation at the period close. The
// period-close dialog surfaces whether the shelves were reconciled (an approved
// stocktake landed in the period): an un-reconciled period warns the operator
// before they lock the books; a reconciled one confirms it.

const BASE = 'http://127.0.0.1:8000/api/v1/production';
const NO_OPEN = { status: 'no_open_shift', shift: null };

const SUMMARY = {
  period_type: 'month',
  year: 2026,
  month: 6,
  period_key: '2026-06',
  shifts_count: 3,
  opening_cash: 300,
  closing_cash: 315,
  expected_cash: 312,
  cash_difference: 3,
  total_sales: 1200,
  total_transactions: 45,
  reconciliation: 'over',
  already_closed: false,
  has_open_shift: false,
  inventory_reconciled: false,
  stock_counts_approved: 0,
  last_reconciled_at: null,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <ShiftManagement />
    </LanguageProvider>
  );
}

function baseHandlers() {
  return [
    http.get(`${BASE}/shifts/current`, () => HttpResponse.json(NO_OPEN)),
    http.get(`${BASE}/shifts/history`, () => HttpResponse.json({ shifts: [], total: 0 })),
    http.get(`${BASE}/shifts/movements`, () =>
      HttpResponse.json({ movements: [], total: 0, pay_in: 0, pay_out: 0, cash_drops: 0 })
    ),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ShiftManagement period close — inventory reconciliation (issue #210)', () => {
  it('warns when the period has no approved stock count', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/period-summary`, () => HttpResponse.json(SUMMARY))
    );

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /period close/i }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(/un-reconciled|no stock count/i)).toBeInTheDocument();
  });

  it('confirms when an approved stock count landed in the period', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/period-summary`, () =>
        HttpResponse.json({
          ...SUMMARY,
          inventory_reconciled: true,
          stock_counts_approved: 2,
          last_reconciled_at: '2026-06-20T10:00:00',
        })
      )
    );

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /period close/i }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(/inventory reconciled/i)).toBeInTheDocument();
  });
});
