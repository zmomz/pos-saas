import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CatalogModifiers from './CatalogModifiers';

// ISSUE-066 — a RETAIL merchant builds modifier groups and combos from the catalog
// UI. The page targets the un-gated /api/v1/catalog surface (vs the restaurant
// menu-builder's /api/v1/restaurant), so a retail business type is not 403'd.

const BASE = 'http://127.0.0.1:8000';

const PRODUCTS = [
  { id: 1, client_id: 1, name: 'Mug', price: 20, quantity: 10, reorder_point: 0, reorder_quantity: 0, is_active: true, is_weighted: false, is_open_price: false },
  { id: 2, client_id: 1, name: 'Coaster', price: 8, quantity: 10, reorder_point: 0, reorder_quantity: 0, is_active: true, is_weighted: false, is_open_price: false },
];

function baseHandlers(groups: Array<Record<string, unknown>>, combos: Array<Record<string, unknown>>) {
  return [
    http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json({ items: PRODUCTS, total: PRODUCTS.length })),
    http.get(`${BASE}/api/v1/catalog/modifier-groups`, () => HttpResponse.json(groups)),
    http.get(`${BASE}/api/v1/catalog/combos`, () => HttpResponse.json(combos)),
    http.get(`${BASE}/api/v1/catalog/products/:pid/modifier-groups`, () => HttpResponse.json({ items: [], total: 0 })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CatalogModifiers />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('CatalogModifiers (retail)', () => {
  it('creates a modifier group on the catalog surface', async () => {
    let posted: Record<string, unknown> | null = null;
    const groups: Array<Record<string, unknown>> = [];
    server.use(
      ...baseHandlers(groups, []),
      http.post(`${BASE}/api/v1/catalog/modifier-groups`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        const created = { id: 7, ...posted };
        groups.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),
    );

    renderPage();

    const nameInput = await screen.findByPlaceholderText(/group name/i);
    await userEvent.type(nameInput, 'Gift wrap');
    await userEvent.click(screen.getByRole('button', { name: /add modifier group/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.name).toBe('Gift wrap');
    expect((await screen.findAllByText('Gift wrap')).length).toBeGreaterThan(0);
  });

  it('defines a combo of two component products on the catalog surface', async () => {
    let posted: Record<string, unknown> | null = null;
    const combos: Array<Record<string, unknown>> = [];
    server.use(
      ...baseHandlers([], combos),
      http.post(`${BASE}/api/v1/catalog/combos`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        const created = { id: 3, component_sum: 28, ...posted };
        combos.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),
    );

    renderPage();

    await userEvent.type(await screen.findByPlaceholderText(/combo name/i), 'Meal deal');
    await userEvent.type(screen.getByPlaceholderText(/bundle price/i), '25');
    await userEvent.click(screen.getByRole('combobox', { name: /components 1/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'Mug' }));
    await userEvent.click(screen.getByRole('combobox', { name: /components 2/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'Coaster' }));
    await userEvent.click(screen.getByRole('button', { name: /add combo/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.name).toBe('Meal deal');
    expect(posted!.bundle_price).toBe(25);
    expect(posted!.components).toEqual([
      { product_id: 1, qty: 1 },
      { product_id: 2, qty: 1 },
    ]);
    expect(await screen.findByText(/Meal deal/)).toBeInTheDocument();
  });
});
