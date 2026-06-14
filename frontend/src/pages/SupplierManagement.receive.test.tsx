import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SupplierManagement from './SupplierManagement';

// ISSUE-037 — Receiving a UI-created PO must land stock for each line and support
// a receive dialog that selects a branch and per-line received quantities (partial
// receipts). The create form already persists `product_id` on each items_json line
// (#36); this covers the receive side: the dialog posts {branch_id, lines:[{product_id,
// quantity}]} to /purchase_orders/{id}/receive, so the backend lands stock per line
// and leaves the PO partially_received when only part of a line is received.

const BASE = 'http://127.0.0.1:8000';

const ONE_SUPPLIER = {
  items: [{ id: '1', name: 'Acme Foods', status: 'active' }],
  total: 1,
};

const PRODUCTS = {
  items: [{ id: 7, name: 'Flour 25kg' }],
  total: 1,
};

const BRANCHES = { items: [{ id: 3, name: 'Downtown' }], total: 1 };

// An ordered PO whose single line carries the product_id the receive flow keys off.
const PO = {
  items: [
    {
      id: '10',
      supplier_id: '1',
      status: 'ordered',
      total_amount: 50,
      items_json: JSON.stringify([
        { product_id: 7, product_name: 'Flour 25kg', quantity: 10, unit_price: 5 },
      ]),
    },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(ONE_SUPPLIER)),
    http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(PO)),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(PRODUCTS)),
    http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(BRANCHES)),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SupplierManagement receive PO (ISSUE-037)', () => {
  it('receives into a selected branch, posting per-line product_id + quantity', async () => {
    let body: { branch_id?: number; lines?: { product_id: number; quantity: number }[] } | undefined;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/entities/purchase_orders/10/receive`, async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ id: '10', status: 'received', received_items: 1, message: 'ok' });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /purchase orders/i }));
    await userEvent.click(await screen.findByRole('button', { name: /^receive$/i }));

    // Branch picker in the receive dialog.
    const branchSelect = await screen.findByRole('combobox');
    await userEvent.selectOptions(branchSelect, '3');

    await userEvent.click(screen.getByRole('button', { name: /receive stock/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body!.branch_id).toBe(3);
    expect(body!.lines).toHaveLength(1);
    expect(body!.lines![0]).toMatchObject({ product_id: 7, quantity: 10 });
  });

  it('posts a partial quantity when a line is received below its remaining', async () => {
    let body: { lines?: { product_id: number; quantity: number }[] } | undefined;
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/api/v1/entities/purchase_orders/10/receive`, async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ id: '10', status: 'partially_received', received_items: 1, message: 'ok' });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /purchase orders/i }));
    await userEvent.click(await screen.findByRole('button', { name: /^receive$/i }));

    // Reduce the per-line received quantity below the remaining 10 → partial receipt.
    const qty = await screen.findByRole('spinbutton');
    await userEvent.clear(qty);
    await userEvent.type(qty, '4');

    await userEvent.click(screen.getByRole('button', { name: /receive stock/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body!.lines).toHaveLength(1);
    expect(body!.lines![0]).toMatchObject({ product_id: 7, quantity: 4 });
  });
});
