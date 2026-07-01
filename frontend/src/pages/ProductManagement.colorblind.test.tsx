import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// ISSUE-226 (M11 FE-Platform · a11y) — color-blind-safe low-stock state. In the
// products table the "stock" cell for a low-stock product was rendered as a red
// `pill-danger` showing ONLY the on-hand number. Color (red) was the sole cue
// distinguishing a low-stock row from a healthy one, so a red/green color-blind
// operator — and any screen-reader user — got no signal at all. WCAG 1.4.1 (use
// of color). The cell must now also carry a NON-COLOR cue: an accessible
// "Low Stock" label rendered alongside the number.

const BASE = 'http://127.0.0.1:8000';

const LOW = {
  id: 1,
  name: 'Widget',
  price: 10,
  quantity: 2,
  reorder_point: 5,
  vat_rate: 15,
  is_active: true,
};

const HEALTHY = {
  id: 2,
  name: 'Gadget',
  price: 20,
  quantity: 50,
  reorder_point: 5,
  vat_rate: 15,
  is_active: true,
};

function mockEndpoints(products: unknown[]) {
  server.use(
    http.get(`${BASE}/api/v1/products/list`, () =>
      HttpResponse.json({ items: products, total: products.length })
    ),
    http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/entities/categories`, () =>
      HttpResponse.json({ items: [], total: 0 })
    )
  );
}

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

describe('ProductManagement color-blind-safe low-stock state (ISSUE-226 a11y)', () => {
  it('carries a non-color "Low Stock" label on a low-stock cell', async () => {
    mockEndpoints([LOW]);
    renderPage();

    const row = (await screen.findByText('Widget')).closest('tr') as HTMLElement;
    // The state is conveyed as an accessible label, not just red styling.
    expect(within(row).getByText(/low stock/i)).toBeInTheDocument();
  });

  it('does not label a healthy stock cell as low', async () => {
    mockEndpoints([HEALTHY]);
    renderPage();

    const row = (await screen.findByText('Gadget')).closest('tr') as HTMLElement;
    expect(within(row).queryByText(/low stock/i)).not.toBeInTheDocument();
  });
});
