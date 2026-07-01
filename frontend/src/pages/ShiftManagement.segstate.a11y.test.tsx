import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The cash-movement dialog's Movement Type selector
// (Pay In / Pay Out / Cash Drop) signalled its selected segment with
// `data-active` (styling) ALONE — no `aria-pressed`, so a screen-reader user
// got no cue which type was active (WCAG 1.4.1 / 4.1.2).

const BASE = 'http://127.0.0.1:8000/api/v1/production';

const OPEN_CURRENT = {
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

describe('ShiftManagement movement-type segmented-control a11y (#226)', () => {
  it('announces the active movement type via aria-pressed', async () => {
    server.use(
      http.get(`${BASE}/shifts/current`, () => HttpResponse.json(OPEN_CURRENT)),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json({ shifts: [], total: 0 })),
      http.get(`${BASE}/shifts/movements`, () => HttpResponse.json({ movements: [] })),
    );
    const user = userEvent.setup();
    renderPage();

    // Open the cash-movement dialog (defaults to 'pay_out').
    await user.click(await screen.findByRole('button', { name: /record cash movement/i }));

    expect(
      await screen.findByRole('button', { name: 'Pay Out', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Pay In', pressed: false })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Cash Drop', pressed: false })
    ).toBeInTheDocument();
  });
});
