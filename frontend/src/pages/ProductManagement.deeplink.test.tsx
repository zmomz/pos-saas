import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// #273 (Productivity follow-up — global-search deep-linking): a ⌘K search hit
// deep-links to /products?q=<barcode|name> instead of the bare catalog. Landing
// there must seed the page's search so the fetch is pre-narrowed to that one
// record — the user sees the thing they searched for, not the whole book.

const BASE = 'http://127.0.0.1:8000';

const CATALOG = [
  { id: 1, name: 'Espresso', barcode: 'BC-ESP', price: 10, quantity: 5, vat_rate: 15, is_active: true },
  { id: 2, name: 'Latte', barcode: 'BC-LAT', price: 12, quantity: 8, vat_rate: 15, is_active: true },
];

function stubEndpoints() {
  server.use(
    // Server-side search: honour the ?search= param the page sends.
    http.get(`${BASE}/api/v1/products/list`, ({ request }) => {
      const term = new URL(request.url).searchParams.get('search')?.toLowerCase();
      const items = term
        ? CATALOG.filter(
            (p) => p.name.toLowerCase().includes(term) || p.barcode.toLowerCase().includes(term),
          )
        : CATALOG;
      return HttpResponse.json({ items, total: items.length });
    }),
    http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
    http.get(`${BASE}/api/v1/entities/categories`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LanguageProvider>
        <ProductManagement />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ProductManagement deep-link (#273)', () => {
  it('seeds the search from ?q= and pre-filters to the linked record', async () => {
    stubEndpoints();
    renderAt('/products?q=BC-LAT');

    // Only the deep-linked product surfaces; the rest of the catalog is filtered out.
    expect(await screen.findByText('Latte')).toBeInTheDocument();
    expect(screen.queryByText('Espresso')).not.toBeInTheDocument();

    // The search box visibly reflects the seed so the filter is discoverable/clearable.
    const searchBox = screen.getByPlaceholderText(/search/i) as HTMLInputElement;
    expect(searchBox.value).toBe('BC-LAT');
  });

  it('shows the whole catalog when there is no ?q=', async () => {
    stubEndpoints();
    renderAt('/products');

    expect(await screen.findByText('Espresso')).toBeInTheDocument();
    expect(await screen.findByText('Latte')).toBeInTheDocument();
  });
});
