import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// M11 · FE-Platform a11y (#226) — native inputs → shadcn on the settle-by-item
// picker. The "bill these exact lines" list rendered raw <input type="checkbox">;
// this swaps in the shared shadcn Checkbox (Radix <button role="checkbox">) so it
// matches the modifier picker and the rest of the design system. The accessible
// name (qty × name) and the toggle behaviour must survive the swap.

const BASE = 'http://127.0.0.1:8000';
const TID = 9;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };
const ITEMS = {
  items: [
    { id: 501, product_id: 1, name: 'Latte', qty: 2, line_total: 30, seat_no: null },
    { id: 502, product_id: 2, name: 'Muffin', qty: 1, line_total: 12, seat_no: null },
  ],
  total: 2,
};

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}`, () => HttpResponse.json(TICKET)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/items`, () => HttpResponse.json(ITEMS)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/check`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/print-routing`, () =>
      HttpResponse.json(null)
    ),
    http.get(`${BASE}/api/v1/restaurant/order-tickets`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/restaurant/tables`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/restaurant/combos`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json([])),
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('OrderTicket settle-by-item picker — shadcn Checkbox (#226)', () => {
  it('renders each billable line as a shadcn Checkbox that toggles', async () => {
    server.use(...baseHandlers());
    renderPage();
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    // Open settle dialog, then switch the scope Select to "by item".
    const settleBtn = await screen.findByRole('button', { name: /^settle$/i });
    await waitFor(() => expect(settleBtn).not.toBeDisabled());
    await user.click(settleBtn);

    const dialog = within(await screen.findByRole('dialog'));
    const scope = dialog.getByRole('combobox', { name: /what to settle/i });
    await user.click(scope);
    const byItem = await screen.findByRole('option', { name: /by item/i });
    await user.click(byItem);

    const latte = await dialog.findByRole('checkbox', { name: /2 × latte/i });
    // Radix Checkbox is a <button role="checkbox">, not a native <input>.
    expect(latte.tagName).toBe('BUTTON');
    expect(latte).toHaveAttribute('aria-checked', 'false');

    await user.click(latte);
    await waitFor(() => expect(latte).toHaveAttribute('aria-checked', 'true'));
  });
});
