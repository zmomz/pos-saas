import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MenuBuilder from './MenuBuilder';

// ISSUE-040 — `attachModifierGroup`/`detachModifierGroup` were exported with no
// caller. The MenuBuilder must let a merchant attach/detach modifier groups to a
// product, persist the change, and surface the attached groups on the product.

const BASE = 'http://127.0.0.1:8000';

const GROUPS = [
  { id: 1, name: 'Size', name_ar: 'الحجم', required: true, min_select: 1, max_select: 1 },
  { id: 2, name: 'Extras', name_ar: 'إضافات', required: false, min_select: 0, max_select: 3 },
];
const PRODUCTS = [{ id: 10, name: 'Burger', price: 20 }];

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MenuBuilder />
      </LanguageProvider>
    </MemoryRouter>
  );
}

// Base read handlers shared by every case. `attached` maps a product id to the
// modifier groups currently attached to it (what GET .../modifier-groups returns).
function baseHandlers(attached: Record<number, typeof GROUPS> = {}) {
  return [
    http.get(`${BASE}/api/v1/restaurant/modifier-groups`, () => HttpResponse.json(GROUPS)),
    http.get(`${BASE}/api/v1/restaurant/modifier-groups/:id/modifiers`, () =>
      HttpResponse.json([])
    ),
    http.get(`${BASE}/api/v1/restaurant/combos`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(PRODUCTS)),
    http.get(`${BASE}/api/v1/restaurant/products/:pid/modifier-groups`, ({ params }) => {
      const items = attached[Number(params.pid)] ?? [];
      return HttpResponse.json({ items, total: items.length });
    }),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MenuBuilder product↔modifier-group attach (ISSUE-040)', () => {
  it('attaches a selected modifier group to a product', async () => {
    let attachCall: { pid?: string; gid?: string } | null = null;
    server.use(
      ...baseHandlers(),
      http.post(
        `${BASE}/api/v1/restaurant/products/:pid/modifier-groups/:gid`,
        ({ params }) => {
          attachCall = { pid: params.pid as string, gid: params.gid as string };
          return HttpResponse.json({ message: 'attached' }, { status: 201 });
        }
      )
    );

    renderPage();

    const card = await screen.findByTestId('product-mods-10');
    await userEvent.click(within(card).getByRole('combobox'));
    await userEvent.click(await screen.findByRole('option', { name: 'Size' }));
    await userEvent.click(within(card).getByRole('button', { name: /^attach$/i }));

    await waitFor(() => expect(attachCall).toEqual({ pid: '10', gid: '1' }));
  });

  it('detaches an already-attached modifier group from a product', async () => {
    let detachCall: { pid?: string; gid?: string } | null = null;
    server.use(
      ...baseHandlers({ 10: [{ ...GROUPS[0], modifiers: [] }] }),
      http.delete(
        `${BASE}/api/v1/restaurant/products/:pid/modifier-groups/:gid`,
        ({ params }) => {
          detachCall = { pid: params.pid as string, gid: params.gid as string };
          return HttpResponse.json({ message: 'detached' });
        }
      )
    );

    renderPage();

    const card = await screen.findByTestId('product-mods-10');
    await userEvent.click(within(card).getByRole('button', { name: /detach size/i }));

    await waitFor(() => expect(detachCall).toEqual({ pid: '10', gid: '1' }));
  });

  it("surfaces a product's already-attached groups and hides them from the attach picker", async () => {
    server.use(...baseHandlers({ 10: [{ ...GROUPS[0], modifiers: [] }] }));

    renderPage();

    const card = await screen.findByTestId('product-mods-10');
    // The attached "Size" group is shown as a removable badge...
    expect(within(card).getByRole('button', { name: /detach size/i })).toBeInTheDocument();
    // ...and is no longer offered in the attach dropdown (only "Extras" remains).
    await userEvent.click(within(card).getByRole('combobox'));
    const optionLabels = (await screen.findAllByRole('option')).map((o) => o.textContent);
    expect(optionLabels).toContain('Extras');
    expect(optionLabels).not.toContain('Size');
  });
});
