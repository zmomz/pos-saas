import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MenuBuilder from './MenuBuilder';

// ISSUE-039 — the BOM/recipe endpoints + sale-core depletion exist, but there was
// no api.ts client and no UI, so a merchant could never define a recipe in-app.
// The MenuBuilder must let a merchant define a recipe (component product + qty-per)
// against a product and remove an existing component, hitting the same
// /products/{id}/bom surface the sale-depletion path consumes.

const BASE = 'http://127.0.0.1:8000';

const PRODUCTS = [
  { id: 10, name: 'Cheeseburger', price: 30 },
  { id: 11, name: 'Bun', price: 1 },
  { id: 12, name: 'Beef', price: 5 },
];

interface BomEntry {
  id: number;
  user_id: string;
  parent_product_id: number;
  component_product_id: number;
  qty_per: number;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MenuBuilder />
      </LanguageProvider>
    </MemoryRouter>
  );
}

// Shared read handlers. `bom` maps a parent product id to its BOM entries (what
// GET .../{id}/bom returns), with a rolled-up cost_of_goods.
function baseHandlers(bom: Record<number, BomEntry[]> = {}) {
  return [
    http.get(`${BASE}/api/v1/restaurant/modifier-groups`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/restaurant/modifier-groups/:id/modifiers`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/restaurant/combos`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(PRODUCTS)),
    http.get(`${BASE}/api/v1/restaurant/products/:pid/modifier-groups`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/restaurant/products/:pid/bom`, ({ params }) => {
      const items = bom[Number(params.pid)] ?? [];
      return HttpResponse.json({ items, total: items.length, cost_of_goods: 0 });
    }),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MenuBuilder recipe / BOM editor (ISSUE-039)', () => {
  it('defines a recipe component (product + qty-per) on a product', async () => {
    let addCall: { pid?: string; body?: unknown } | null = null;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/restaurant/products/:pid/bom`, async ({ params, request }) => {
        addCall = { pid: params.pid as string, body: await request.json() };
        return HttpResponse.json(
          { id: 1, user_id: 'u', parent_product_id: 10, component_product_id: 11, qty_per: 2 },
          { status: 201 }
        );
      })
    );

    renderPage();

    const card = await screen.findByTestId('product-bom-10');
    await userEvent.selectOptions(within(card).getByRole('combobox'), '11');
    const qty = within(card).getByLabelText(/qty per/i);
    await userEvent.clear(qty);
    await userEvent.type(qty, '2');
    await userEvent.click(within(card).getByRole('button', { name: /add component/i }));

    await waitFor(() =>
      expect(addCall).toEqual({ pid: '10', body: { component_product_id: 11, qty_per: 2 } })
    );
  });

  it('surfaces an existing recipe component and removes it', async () => {
    let deleteId: string | null = null;
    server.use(
      ...baseHandlers({
        10: [
          { id: 7, user_id: 'u', parent_product_id: 10, component_product_id: 11, qty_per: 1 },
        ],
      }),
      http.delete(`${BASE}/api/v1/restaurant/bom/:bomId`, ({ params }) => {
        deleteId = params.bomId as string;
        return HttpResponse.json({ message: 'deleted', id: Number(params.bomId) });
      })
    );

    renderPage();

    const card = await screen.findByTestId('product-bom-10');
    // The Bun component is surfaced as a removable row...
    const removeBtn = within(card).getByRole('button', { name: /remove bun/i });
    expect(removeBtn).toBeInTheDocument();
    // ...and is no longer offered as a component to add (only Beef remains; not self).
    const select = within(card).getByRole('combobox') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toContain('Beef');
    expect(labels).not.toContain('Bun');
    expect(labels).not.toContain('Cheeseburger');

    await userEvent.click(removeBtn);
    await waitFor(() => expect(deleteId).toBe('7'));
  });
});
