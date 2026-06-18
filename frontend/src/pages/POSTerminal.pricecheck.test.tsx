import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-076 — price / stock check. A cashier can scan/search a SKU to see its
// current price and on-hand stock WITHOUT adding it to the cart. The lookup goes
// through the same authoritative /pos/resolve-barcode endpoint as a scan-to-add,
// but in "price check" mode it only displays the result.

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

describe('POSTerminal price / stock check (ISSUE-076)', () => {
  it('shows current price and on-hand stock for a scanned SKU', async () => {
    server.use(
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      http.get(`${BASE}/pos/resolve-barcode`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get('barcode')).toBe('WIDGET-1');
        return HttpResponse.json({
          kind: 'product',
          product_id: 5,
          name: 'Widget',
          price: 9.5,
          quantity: 7,
          barcode: 'WIDGET-1',
        });
      }),
      ...mountSideHandlers()
    );

    renderPage();

    // Switch the scanner into price-check (lookup-only) mode.
    await userEvent.click(await screen.findByRole('button', { name: /price check/i }));

    // Scan / type the SKU and submit.
    const scanInput = screen.getByPlaceholderText(/scan barcode/i);
    await userEvent.type(scanInput, 'WIDGET-1{Enter}');

    // The product's current price and on-hand stock are shown.
    await waitFor(() => expect(screen.getByText('Widget')).toBeInTheDocument());
    expect(screen.getByText(/9\.50\s*⃁/)).toBeInTheDocument();
    expect(screen.getByText(/7/)).toBeInTheDocument();
  });

  it('does not add the looked-up product to the cart', async () => {
    server.use(
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      http.get(`${BASE}/pos/resolve-barcode`, () =>
        HttpResponse.json({
          kind: 'product',
          product_id: 5,
          name: 'Widget',
          price: 9.5,
          quantity: 7,
          barcode: 'WIDGET-1',
        })
      ),
      ...mountSideHandlers()
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /price check/i }));
    const scanInput = screen.getByPlaceholderText(/scan barcode/i);
    await userEvent.type(scanInput, 'WIDGET-1{Enter}');

    // Result is shown...
    await waitFor(() => expect(screen.getByText('Widget')).toBeInTheDocument());
    // ...but the cart stays empty (lookup must not modify the cart).
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });
});
