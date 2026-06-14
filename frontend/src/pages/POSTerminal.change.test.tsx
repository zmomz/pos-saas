import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-074 — cash-drawer change-due helper. On a cash payment the cashier enters
// the amount the customer handed over; the UI shows the change owed back and the
// checkout sends `cash_tendered` so the backend records tendered + change on the
// sale.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal cash change-due helper (ISSUE-074)', () => {
  it('shows change owed and sends cash_tendered on a cash sale', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.get(PRODUCTS_URL, () =>
        HttpResponse.json([{ id: 1, name: 'Juice', price: 12, vat_rate: 0.15 }])
      ),
      http.post(`${BASE}/pos/transaction`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          invoice_number: 'INV-1',
          total_amount: 13.8,
          vat_amount: 1.8,
          subtotal: 12,
          payment_method: 'cash',
          cash_tendered: 20,
          change_due: 6.2,
        });
      }),
      ...mountSideHandlers()
    );

    renderPage();

    // Add the product (amount due = 12 + 1.8 VAT = 13.80); cash is the default method.
    await userEvent.click(await screen.findByText('Juice'));

    // Enter the cash the customer handed over.
    const tenderInput = await screen.findByLabelText(/cash tendered/i);
    await userEvent.clear(tenderInput);
    await userEvent.type(tenderInput, '20');

    // The change owed back (20 - 13.80 = 6.20) is shown to the cashier.
    await waitFor(() => expect(screen.getByText(/6\.20/)).toBeInTheDocument());

    // Settle the sale.
    await userEvent.click(screen.getByRole('button', { name: /^pay\b/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.cash_tendered).toBe(20);
    expect(posted!.payment_method).toBe('cash');
  });
});
