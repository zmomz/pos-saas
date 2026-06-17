import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// ISSUE-072 — a cashier adds a gratuity at the settle dialog. The tip rides on
// TOP of the invoice total (goods + VAT + service charge) and never touches the
// VAT base, so the dialog must show the tip added to the amount due and ship a
// `tip_amount` on the settle call. Backend already records + renders the tip.

const BASE = 'http://127.0.0.1:8000';
const TID = 7;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };
const ITEMS = {
  items: [
    { id: 1, ticket_id: TID, name: 'Shawarma', qty: 1, unit_price: 100, line_total: 100 },
  ],
  total: 1,
};
// goods 100 + 15% VAT = 115.00 amount due, no service charge, no tip.
const CHECK = {
  ticket_id: TID,
  lines: [{ item_id: 1, name: 'Shawarma', qty: 1, unit_price: 100, line_total: 100, taxable: true }],
  subtotal: 100,
  vat_rate: 0.15,
  vat_amount: 15,
  total_amount: 115,
  service_charge: { pct: 0, amount: 0, taxable: false },
  tip_amount: 0,
  amount_due: 115,
};

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}`, () => HttpResponse.json(TICKET)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/items`, () => HttpResponse.json(ITEMS)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/check`, () => HttpResponse.json(CHECK)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/print-routing`, () =>
      HttpResponse.json(null)
    ),
    http.get(`${BASE}/api/v1/restaurant/order-tickets`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/restaurant/tables`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/restaurant/combos`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json({ items: [], total: 0 })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/restaurant/tickets/${TID}`]}>
      <LanguageProvider>
        <Routes>
          <Route path="/restaurant/tickets/:ticketId" element={<OrderTicket />} />
        </Routes>
      </LanguageProvider>
    </MemoryRouter>
  );
}

async function openSettleDialog() {
  const settleBtn = await screen.findByRole('button', { name: /^settle$/i });
  await userEvent.click(settleBtn);
  return within(await screen.findByRole('dialog'));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Tip entry on settle dialog (ISSUE-072)', () => {
  it('records the entered tip on the settle call (AC1)', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/restaurant/order-tickets/${TID}/settle`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ticket_id: TID,
          transaction_id: 1,
          invoice_number: 'INV-1',
          subtotal: 100,
          vat_amount: 15,
          total_amount: 115,
          service_charge: 0,
          tip_amount: 10,
          amount_due: 115,
          zatca_status: 'disabled',
          ticket_status: 'settled',
          table_freed: true,
        });
      })
    );

    renderPage();
    const dialog = await openSettleDialog();

    const tip = dialog.getByLabelText(/tip/i);
    await userEvent.clear(tip);
    await userEvent.type(tip, '10');

    await userEvent.click(dialog.getByRole('button', { name: /^settle$/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect((posted as Record<string, unknown>).tip_amount).toBe(10);
  });

  it('adds the tip on top of the amount due without changing the VAT base (AC2)', async () => {
    server.use(...baseHandlers());

    renderPage();
    const dialog = await openSettleDialog();

    const tip = dialog.getByLabelText(/tip/i);
    await userEvent.clear(tip);
    await userEvent.type(tip, '10');

    // Tip rides on top: total to charge = 115.00 + 10 = 125.00.
    expect(await dialog.findByText('125.00 SAR')).toBeInTheDocument();
    // The VAT-bearing amount due is untouched.
    expect(dialog.getByText('115.00 SAR')).toBeInTheDocument();
  });
});
