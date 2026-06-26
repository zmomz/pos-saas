import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { toast } from 'sonner';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// FE-04 — OrderTicket mutation handlers (add/void/fire/transfer/merge/split/
// service-charge) swallowed failures to console.error, so a rejected action
// looked like a no-op. A failure now raises a visible error toast.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000';
const TID = 7;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };
const ITEMS = {
  items: [{ id: 1, ticket_id: TID, name: 'Shawarma', qty: 1, unit_price: 100, line_total: 100, seat_no: 1 }],
  total: 1,
};

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}`, () => HttpResponse.json(TICKET)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/items`, () => HttpResponse.json(ITEMS)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/check`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/print-routing`, () => HttpResponse.json(null)),
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});
afterAll(() => server.close());

describe('OrderTicket mutation failure surfacing (FE-04)', () => {
  it('toasts the server error when voiding a line fails', async () => {
    server.use(
      ...baseHandlers(),
      http.delete(`${BASE}/api/v1/restaurant/order-tickets/${TID}/items/1`, () =>
        HttpResponse.json({ detail: 'Line already fired' }, { status: 409 })
      )
    );

    renderPage();

    const voidBtn = await screen.findByRole('button', { name: /^void$/i });
    await userEvent.click(voidBtn);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Line already fired'));
  });
});
