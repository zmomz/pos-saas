import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-050 (H16): the integrated-terminal charge path was unreachable from the
// POS — `POSTerminal` never sent `terminal_id`, so a card leg always went to the
// online gateway even when the merchant had paired an in-store SoftPOS terminal.
// `sale_core` already honours `payment_terminal_id` (routes the charge to the
// terminal gateway); this pins the missing UI half: a checkout terminal picker
// that puts the chosen terminal on the sale.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
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

describe('POSTerminal checkout terminal picker (ISSUE-050 / H16)', () => {
  it('routes a card sale to the picked terminal — the transaction carries payment_terminal_id', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.get(PRODUCTS_URL, () =>
        HttpResponse.json([{ id: 1, name: 'Juice', price: 12, vat_rate: 0.15 }])
      ),
      http.get(`${BASE}/payments/terminals`, () =>
        HttpResponse.json([
          { id: 7, provider: 'geidea', label: 'Front lane', serial: 'GEI-007', status: 'active' },
        ])
      ),
      http.post(`${BASE}/pos/transaction`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          invoice_number: 'INV-1',
          total_amount: 13.8,
          vat_amount: 1.8,
          subtotal: 12,
          payment_method: 'mada',
          tenders: [{ tender_type: 'mada', gateway: 'geidea' }],
        });
      }),
      ...mountSideHandlers()
    );

    renderPage();

    // Add the product to the cart.
    await userEvent.click(await screen.findByText('Juice'));
    // Pay by card-like tender (mada), then pick the paired terminal.
    await userEvent.click(screen.getByRole('button', { name: /mada/i }));
    await userEvent.click(screen.getByRole('button', { name: /front lane/i }));
    // Settle the sale.
    await userEvent.click(screen.getByRole('button', { name: /^pay\b/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.payment_terminal_id).toBe(7);
    expect(posted!.payment_method).toBe('mada');
  });
});
