import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// ISSUE-021 — `/products/list` returns `ProductListResponse { items, total }`,
// but the page used to read `data?.products`, leaving the primary catalog table
// permanently empty. The table must render `items` and the count reflect `total`.

const BASE = 'http://127.0.0.1:8000';

const PRODUCTS = {
  items: [
    { id: 1, name: 'Espresso', price: 10, quantity: 5, vat_rate: 15, is_active: true },
    { id: 2, name: 'Latte', price: 12, quantity: 8, vat_rate: 15, is_active: true },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ProductManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ProductManagement catalog table (ISSUE-021)', () => {
  it('renders the products returned under `items` by /products/list', async () => {
    server.use(
      http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(PRODUCTS)),
      http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
        HttpResponse.json({ items: [], total: 0 })
      )
    );

    renderPage();

    expect(await screen.findByText('Espresso')).toBeInTheDocument();
    expect(await screen.findByText('Latte')).toBeInTheDocument();
  });

  it('shows the total product count from the response', async () => {
    server.use(
      http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(PRODUCTS)),
      http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
        HttpResponse.json({ items: [], total: 0 })
      )
    );

    renderPage();

    // Wait for the catalog to populate, then assert the "Total Products" tile.
    await screen.findByText('Espresso');
    const totalTile = screen.getByText('Total Products').closest('div');
    expect(totalTile).toHaveTextContent('2');
  });
});
