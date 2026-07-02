import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the refund flow's
// per-line "how many to return" steppers.
//
// Once a sale is picked for refund, each line exposes a −/+ stepper plus a
// number field to choose the return quantity. Those controls carried NO
// accessible name: the buttons announced only their bare glyph ("minus"/"plus")
// and the number field announced only "spin button", neither tied to the item
// being refunded — WCAG 4.1.2 (Name, Role, Value). A screen-reader cashier
// refunding a multi-line sale could not tell which line a stepper belonged to.
// This slice names all three controls after the line item, matching the labelled
// cart steppers on the sell side.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

const TXNS = [
  {
    id: 1,
    invoice_number: 'INV-1001',
    created_at: '2026-06-30T10:00:00Z',
    total_amount: 45,
    payment_method: 'cash',
    items: [{ product_id: 1, name: 'Latte', price: 15, quantity: 3 }],
  },
];

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(PRODUCTS_URL, () => HttpResponse.json([])),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json({ items: TXNS })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

async function openRefundLineFor(invoice: RegExp) {
  const refundBtn = await screen.findByRole('button', { name: /^refund$/i });
  await userEvent.click(refundBtn);
  const row = await screen.findByRole('button', { name: invoice });
  await userEvent.click(row);
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal refund-line steppers a11y (#226)', () => {
  it('names the decrease-quantity button after the line item', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await openRefundLineFor(/INV-1001/);

    expect(
      await screen.findByRole('button', { name: /decrease quantity.*latte/i })
    ).toBeInTheDocument();
  });

  it('names the increase-quantity button after the line item', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await openRefundLineFor(/INV-1001/);

    expect(
      await screen.findByRole('button', { name: /increase quantity.*latte/i })
    ).toBeInTheDocument();
  });

  it('gives the return-quantity field an accessible name tied to the line item', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await openRefundLineFor(/INV-1001/);

    expect(
      await screen.findByRole('spinbutton', { name: /quantity.*latte/i })
    ).toBeInTheDocument();
  });
});
