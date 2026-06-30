import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// Issue #210 (M3·POS) — a closed shift can be reopened from the history table.
// With NO shift currently open, each closed row exposes a Reopen action that
// posts to `POST /shifts/{id}/reopen` with the operator's reason; on success the
// page reloads and the reopened shift shows as Active.

const BASE = 'http://127.0.0.1:8000/api/v1/production';

const CLOSED_HISTORY = {
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

describe('ShiftManagement reopen (issue #210)', () => {
  it('reopens a closed shift with a reason and shows it active', async () => {
    // First /current read: no open shift. After reopen: shift 41 is open.
    let reopened = false;
    const reopenBody = vi.fn();
    server.use(
      http.get(`${BASE}/shifts/current`, () =>
        reopened
          ? HttpResponse.json({
              status: 'open',
              shift: { id: 41, start_time: '2026-06-02T08:00:00+00:00', opening_cash: 100, total_sales: 250, total_transactions: 12, staff_name: 'Cashier A', branch_id: null, notes: 'Reopened: Miscount' },
            })
          : HttpResponse.json({ status: 'no_open_shift', shift: null })
      ),
      http.get(`${BASE}/shifts/history`, () =>
        HttpResponse.json(reopened ? { shifts: [], total: 0 } : CLOSED_HISTORY)
      ),
      http.get(`${BASE}/shifts/movements`, () => HttpResponse.json({ movements: [], total: 0, pay_in: 0, pay_out: 0, cash_drops: 0 })),
      http.post(`${BASE}/shifts/41/reopen`, async ({ request }) => {
        reopenBody(await request.json());
        reopened = true;
        return HttpResponse.json({ id: 41, status: 'open', start_time: '2026-06-02T08:00:00+00:00', end_time: null, opening_cash: 100, closing_cash: null, staff_name: 'Cashier A', branch_id: null, notes: 'Reopened: Miscount' });
      })
    );

    const user = userEvent.setup();
    renderPage();

    // The closed shift is in history; a Reopen control is offered.
    const reopenBtn = await screen.findByRole('button', { name: /reopen/i });
    await user.click(reopenBtn);

    // A reason is required; type it and confirm.
    const reasonInput = await screen.findByLabelText(/reason/i);
    await user.type(reasonInput, 'Miscount');
    const confirmBtn = screen.getByRole('button', { name: /confirm reopen/i });
    await user.click(confirmBtn);

    // The endpoint was hit with the typed reason...
    await waitFor(() => expect(reopenBody).toHaveBeenCalledWith({ reason: 'Miscount' }));
    // ...and after the reload the reopened shift shows as Active.
    expect(await screen.findByText('Active')).toBeInTheDocument();
  });

  it('does not offer Reopen while a shift is already open', async () => {
    server.use(
      http.get(`${BASE}/shifts/current`, () =>
        HttpResponse.json({
          status: 'open',
          shift: { id: 42, start_time: '2026-06-03T08:00:00+00:00', opening_cash: 500, total_sales: 0, total_transactions: 0, staff_name: 'Morning', branch_id: null, notes: null },
        })
      ),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(CLOSED_HISTORY)),
      http.get(`${BASE}/shifts/movements`, () => HttpResponse.json({ movements: [], total: 0, pay_in: 0, pay_out: 0, cash_drops: 0 }))
    );

    renderPage();

    expect(await screen.findByText('Active')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument();
  });
});
