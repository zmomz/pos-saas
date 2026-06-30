import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// Issue #210 (M3·POS) — month-end / year-end period close. The Shift Management
// screen can roll every closed shift in a calendar month into one reconciled
// summary and lock it: opening the dialog previews the roll-up, and confirming
// POSTs the close.

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

describe('ShiftManagement period close (issue #210)', () => {
  it('previews the period roll-up when the period-close dialog opens', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/period-summary`, () => HttpResponse.json(SUMMARY))
    );

    const user = userEvent.setup();
    renderPage();

    const openBtn = await screen.findByRole('button', { name: /period close/i });
    await user.click(openBtn);

    const dialog = await screen.findByRole('dialog');
    // The roll-up names how many shifts are in the period.
    expect(await within(dialog).findByText(/3 shift/i)).toBeInTheDocument();
    // And surfaces the period key being closed.
    expect(within(dialog).getByText(/2026-06/)).toBeInTheDocument();
  });

  it('POSTs the period close with the current month when confirmed', async () => {
    const closeBody = vi.fn();
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/shifts/period-summary`, () => HttpResponse.json(SUMMARY)),
      http.post(`${BASE}/shifts/period-close`, async ({ request }) => {
        closeBody(await request.json());
        return HttpResponse.json({ ...SUMMARY, already_closed: true, closed_at: '2026-06-30T12:00:00+00:00' });
      })
    );

    const user = userEvent.setup();
    renderPage();

    const openBtn = await screen.findByRole('button', { name: /period close/i });
    await user.click(openBtn);

    const dialog = await screen.findByRole('dialog');
    const confirm = await within(dialog).findByRole('button', { name: /close period/i });
    await user.click(confirm);

    await waitFor(() =>
      expect(closeBody).toHaveBeenCalledWith(
        expect.objectContaining({ period_type: 'month' })
      )
    );
    const sent = closeBody.mock.calls[0][0];
    expect(typeof sent.year).toBe('number');
    expect(typeof sent.month).toBe('number');
  });
});
