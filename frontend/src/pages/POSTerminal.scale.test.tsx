import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-230 (Integrations) — retail-scale embedded barcode. Scanning a
// variable-measure scale barcode resolves the product via /pos/resolve-barcode
// and the scan carries the weighed quantity (weighted product), which the cart
// applies to the line instead of the usual "+1".

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

describe('POSTerminal scale barcode (ISSUE-230)', () => {
  it('adds a weighted line with the scanned weight as the quantity', async () => {
    const weighted = {
      id: 42,
      name: 'Bananas',
      price: 6.0,
      quantity: 100,
      is_weighted: true,
      unit_label: 'kg',
      barcode: '2000420000009',
    };
    server.use(
      http.get(PRODUCTS_URL, () => HttpResponse.json([weighted])),
      http.get(`${BASE}/pos/resolve-barcode`, () =>
        HttpResponse.json({
          kind: 'product',
          product_id: 42,
          name: 'Bananas',
          price: 6.0,
          quantity: 100,
          barcode: '2000420012347',
          scale: true,
          scale_kind: 'weight',
          scale_weight: 1.234,
        })
      ),
      ...mountSideHandlers()
    );

    renderPage();

    // Default (add-to-cart) mode: scan the scale barcode.
    const scanInput = await screen.findByPlaceholderText(/scan barcode/i);
    await userEvent.type(scanInput, '2000420012347{Enter}');

    // The weighted line lands in the cart carrying the scanned weight (1.234 kg),
    // NOT a unit count of 1.
    const qtyInput = await screen.findByDisplayValue('1.234');
    expect(qtyInput).toBeInTheDocument();
    // Bananas appears both in the product grid and now in the cart line.
    expect(screen.getAllByText('Bananas').length).toBeGreaterThanOrEqual(2);
  });
});
