import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — keyboard-only nav + screen-reader pass on the
// refund flow's transaction picker.
//
// In refund mode the cashier picks the sale to refund from a list of recent
// transactions. Each row was a bare clickable <div> (cursor-pointer + onClick):
// not in the tab order, not operable by keyboard, and announced as plain text
// rather than a selectable control — WCAG 2.1.1 (keyboard) / 4.1.2 (name, role,
// value). The selected row was also signalled by colour alone (brand ring).
// This slice promotes each row to a real, keyboard-operable button that exposes
// its selected state via `aria-pressed`.

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
  {
    id: 2,
    invoice_number: 'INV-1002',
    created_at: '2026-06-30T11:00:00Z',
    total_amount: 30,
    payment_method: 'card',
    items: [{ product_id: 2, name: 'Burger', price: 30, quantity: 1 }],
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

async function enterRefundMode() {
  const refundBtn = await screen.findByRole('button', { name: /^refund$/i });
  await userEvent.click(refundBtn);
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal refund-picker a11y (#226)', () => {
  it('exposes each transaction row as a keyboard-operable button', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await enterRefundMode();

    // The row is a real button (in the tab order, screen-reader announced as a
    // control), named by its invoice number — not a bare clickable <div>.
    const row = await screen.findByRole('button', { name: /INV-1001/ });
    expect(row).toHaveAttribute('aria-pressed', 'false');
  });

  it('selects a transaction with the keyboard and reflects it via aria-pressed', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await enterRefundMode();

    const row = await screen.findByRole('button', { name: /INV-1001/ });
    row.focus();
    await userEvent.keyboard('{Enter}');

    await waitFor(() => expect(row).toHaveAttribute('aria-pressed', 'true'));
  });
});
