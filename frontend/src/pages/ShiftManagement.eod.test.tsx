import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// Issue #210 (M3·POS) — the end-of-day checklist gates the shift close. When a
// held (parked) ticket is still outstanding, opening the Close dialog surfaces
// the blocking item and the close is refused until either the work is settled or
// a manager forces it with a reason (which the backend audits).

const BASE = 'http://127.0.0.1:8000/api/v1/production';

const OPEN_SHIFT = {
  status: 'open',
  shift: {
    id: 7,
    start_time: '2026-06-30T08:00:00+00:00',
    opening_cash: 100,
    total_sales: 250,
    total_transactions: 12,
    staff_name: 'Cashier A',
    branch_id: null,
    notes: null,
  },
};

const NOT_READY = {
  ready_to_close: false,
  items: [{ key: 'no_held_orders', label: 'No held tickets', blocking: true, satisfied: false, count: 2 }],
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
    http.get(`${BASE}/shifts/current`, () => HttpResponse.json(OPEN_SHIFT)),
    http.get(`${BASE}/shifts/history`, () => HttpResponse.json({ shifts: [], total: 0 })),
    http.get(`${BASE}/shifts/movements`, () =>
      HttpResponse.json({ movements: [], total: 0, pay_in: 0, pay_out: 0, cash_drops: 0 })
    ),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ShiftManagement EOD checklist gate (issue #210)', () => {
  it('surfaces the blocking held-ticket item when the close dialog opens', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/eod-checklist`, () => HttpResponse.json(NOT_READY))
    );

    const user = userEvent.setup();
    renderPage();

    const openClose = await screen.findByRole('button', { name: /close shift/i });
    await user.click(openClose);

    // The dialog warns the drawer is not ready and names the parked tickets.
    expect(await screen.findByText(/held/i)).toBeInTheDocument();
    // A blocking, unsatisfied checklist gates the close behind an override reason.
    expect(await screen.findByLabelText(/override reason/i)).toBeInTheDocument();
  });

  it('forces the close with an override reason when the checklist is not ready', async () => {
    const closeBody = vi.fn();
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/eod-checklist`, () => HttpResponse.json(NOT_READY)),
      http.post(`${BASE}/shifts/close`, async ({ request }) => {
        closeBody(await request.json());
        return HttpResponse.json({ id: 7, status: 'closed', reconciliation: 'balanced' });
      })
    );

    const user = userEvent.setup();
    renderPage();

    const openClose = await screen.findByRole('button', { name: /close shift/i });
    await user.click(openClose);

    const dialog = await screen.findByRole('dialog');
    const closingCash = within(dialog).getByPlaceholderText('0.00');
    await user.clear(closingCash);
    await user.type(closingCash, '350');

    const reasonInput = await within(dialog).findByLabelText(/override reason/i);
    await user.type(reasonInput, 'End of day; ticket abandoned');

    const forceBtn = within(dialog).getByRole('button', { name: /override & close/i });
    await user.click(forceBtn);

    await waitFor(() =>
      expect(closeBody).toHaveBeenCalledWith(
        expect.objectContaining({ override: true, override_reason: 'End of day; ticket abandoned' })
      )
    );
  });
});
