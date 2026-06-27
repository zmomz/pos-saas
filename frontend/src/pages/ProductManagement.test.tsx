import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
    // The label sits in a StatTile whose large value is a sibling node; assert on
    // the enclosing StatTile (the rounded-[20px] card) so the computed total is checked.
    const totalTile = screen.getByText('Total Products').closest('.rounded-\\[20px\\]');
    expect(totalTile).toHaveTextContent('2');
  });
});

// ISSUE-064 — uploading a CSV posts it to the import endpoint and surfaces the
// per-run result (created/updated counts + rejected rows), then refreshes.
describe('ProductManagement CSV import (ISSUE-064)', () => {
  it('uploads a CSV and renders the import summary with rejected rows', async () => {
    server.use(
      http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(PRODUCTS)),
      http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      // The page loads its category tree on mount (ISSUE-038); without a handler
      // the unmatched request trips `onUnhandledRequest: 'error'` and the import
      // summary never renders (REV-05).
      http.get(`${BASE}/api/v1/entities/categories`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.post(`${BASE}/api/v1/entities/products/import`, () =>
        HttpResponse.json({
          created: 3,
          updated: 1,
          total_rows: 5,
          errors: [{ row: 4, errors: ['name: required'] }],
        })
      )
    );

    renderPage();
    await screen.findByText('Espresso');

    const input = screen.getByTestId('csv-import-input') as HTMLInputElement;
    const file = new File(['name,price\nGum,1\n'], 'catalog.csv', { type: 'text/csv' });
    await userEvent.upload(input, file);

    expect(
      await screen.findByText('Imported 3 new and updated 1 products.')
    ).toBeInTheDocument();
    expect(screen.getByText('1 row(s) were rejected:')).toBeInTheDocument();
    expect(screen.getByText(/name: required/)).toBeInTheDocument();
  });
});
