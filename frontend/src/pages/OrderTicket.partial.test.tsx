import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { selectOption } from '../test/selectOption';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// ISSUE-070 — the backend already mints a partial ZATCA invoice from a subset of a
// ticket (by seat or by item) via `POST .../settle-partial`, leaving the remainder
// open. This is the missing frontend slice: the settle dialog must let a server
// choose to settle the WHOLE ticket (existing /settle) OR a single seat's lines OR
// a chosen set of lines, driving the partial endpoint with seat_no / item_ids.

const BASE = 'http://127.0.0.1:8000';
const TID = 7;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };
const ITEMS = {
  items: [
    { id: 1, ticket_id: TID, name: 'Shawarma', qty: 1, unit_price: 100, line_total: 100, seat_no: 1 },
    { id: 2, ticket_id: TID, name: 'Juice', qty: 1, unit_price: 20, line_total: 20, seat_no: 2 },
  ],
  total: 2,
};
const CHECK = {
  ticket_id: TID,
  lines: [
    { item_id: 1, name: 'Shawarma', qty: 1, unit_price: 100, line_total: 100, taxable: true },
    { item_id: 2, name: 'Juice', qty: 1, unit_price: 20, line_total: 20, taxable: true },
  ],
  subtotal: 120,
  vat_rate: 0.15,
  vat_amount: 18,
  total_amount: 138,
  service_charge: { pct: 0, amount: 0, taxable: false },
  tip_amount: 0,
  amount_due: 138,
};

function partialResponse() {
  return HttpResponse.json({
    ticket_id: TID,
    transaction_id: 1,
    invoice_number: 'INV-P1',
    subtotal: 20,
    vat_amount: 3,
    total_amount: 23,
    service_charge: 0,
    tip_amount: 0,
    amount_due: 23,
    zatca_status: 'disabled',
    ticket_status: 'open',
    table_freed: false,
    fully_settled: false,
  });
}

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

describe('Partial settlement UI (ISSUE-070)', () => {
  it('settles a single seat via the partial endpoint with seat_no (AC: by seat)', async () => {
    let posted: Record<string, unknown> | null = null;
    let hitFullSettle = false;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/restaurant/order-tickets/${TID}/settle-partial`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return partialResponse();
      }),
      http.post(`${BASE}/api/v1/restaurant/order-tickets/${TID}/settle`, () => {
        hitFullSettle = true;
        return HttpResponse.json({});
      })
    );

    renderPage();
    const dialog = await openSettleDialog();

    // Choose the "by seat" scope, then pick seat 2.
    await selectOption(dialog.getByLabelText(/what to settle/i), /by seat/i);
    await selectOption(dialog.getByLabelText(/^seat$/i), /seat 2/i);

    await userEvent.click(dialog.getByRole('button', { name: /^settle$/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect((posted as Record<string, unknown>).seat_no).toBe(2);
    expect(hitFullSettle).toBe(false);
  });

  it('settles chosen lines via the partial endpoint with item_ids (AC: by item)', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/restaurant/order-tickets/${TID}/settle-partial`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return partialResponse();
      })
    );

    renderPage();
    const dialog = await openSettleDialog();

    // Choose the "by item" scope, then tick the Shawarma line (id 1).
    await selectOption(dialog.getByLabelText(/what to settle/i), /by item/i);
    await userEvent.click(dialog.getByLabelText(/Shawarma/));

    await userEvent.click(dialog.getByRole('button', { name: /^settle$/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect((posted as Record<string, unknown>).item_ids).toEqual([1]);
  });

  it('still settles the whole ticket via /settle when scope is the whole ticket', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/restaurant/order-tickets/${TID}/settle`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ticket_id: TID,
          transaction_id: 9,
          invoice_number: 'INV-9',
          subtotal: 120,
          vat_amount: 18,
          total_amount: 138,
          service_charge: 0,
          tip_amount: 0,
          amount_due: 138,
          zatca_status: 'disabled',
          ticket_status: 'settled',
          table_freed: true,
          fully_settled: true,
        });
      })
    );

    renderPage();
    const dialog = await openSettleDialog();
    await userEvent.click(dialog.getByRole('button', { name: /^settle$/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect((posted as Record<string, unknown>).item_ids).toBeUndefined();
    expect((posted as Record<string, unknown>).seat_no).toBeUndefined();
  });
});
