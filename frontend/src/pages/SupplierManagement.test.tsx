import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SupplierManagement from './SupplierManagement';

// ISSUE-063 — suppliers capture/store/display a VAT (TRN) number. The list shows
// each supplier's VAT number, and the Add form captures it on create.

const BASE = 'http://127.0.0.1:8000';

const ONE_SUPPLIER = {
  items: [
    {
      id: '1',
      name: 'Acme Foods',
      contact_person: 'Sara',
      email: 'sara@acme.test',
      phone: '+966500000000',
      payment_terms: 'Net 30',
      vat_number: '300000000000003',
      status: 'active',
    },
  ],
  total: 1,
};

const EMPTY = { items: [], total: 0 };

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SupplierManagement VAT number (ISSUE-063)', () => {
  it("displays a supplier's VAT number in the list", async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(ONE_SUPPLIER)),
      http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(EMPTY))
    );

    renderPage();

    expect(await screen.findByText('300000000000003')).toBeInTheDocument();
  });

  it('captures the VAT number when adding a supplier', async () => {
    let createdVat: string | undefined;
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(EMPTY)),
      http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(EMPTY)),
      http.post(`${BASE}/api/v1/entities/suppliers`, async ({ request }) => {
        const body = (await request.json()) as { vat_number?: string };
        createdVat = body.vat_number;
        return HttpResponse.json({ id: '2', name: 'New Co', vat_number: body.vat_number }, { status: 201 });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /add supplier/i }));
    await userEvent.type(await screen.findByPlaceholderText(/company name/i), 'New Co');
    await userEvent.type(screen.getByPlaceholderText(/300000000000003/), '300000000000003');
    // The dialog's submit button.
    await userEvent.click(screen.getByRole('button', { name: /^add supplier$/i }));

    await waitFor(() => expect(createdVat).toBe('300000000000003'));
  });
});

// ISSUE-036 — Creating a PO from the UI must map to the real `Purchase_orders`
// schema: a generated `order_number` (NOT NULL, no default), line items in
// `items_json` carrying `product_id`, and none of the phantom fields the old
// payload sent (`items`, `items_count`, `supplier_name`, `order_date`) that
// caused a 422 / dropped lines.
const PRODUCTS = {
  items: [
    { id: 7, name: 'Flour 25kg' },
    { id: 9, name: 'Sugar 50kg' },
  ],
  total: 2,
};

describe('SupplierManagement create PO (ISSUE-036)', () => {
  it('posts a valid PO body: generated order_number + items_json with product_id, no phantom fields', async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(ONE_SUPPLIER)),
      http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(PRODUCTS)),
      http.post(`${BASE}/api/v1/entities/purchase_orders`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: '10', ...body }, { status: 201 });
      })
    );

    renderPage();

    // Open the Create PO dialog for the seeded supplier.
    await userEvent.click(await screen.findByRole('button', { name: /^PO$/i }));

    // Pick a real product on the line (gives us its product_id) and a quantity.
    const productSelect = await screen.findByRole('combobox');
    await userEvent.selectOptions(productSelect, '7');

    await userEvent.click(screen.getByRole('button', { name: /create purchase order/i }));

    await waitFor(() => expect(body).toBeDefined());

    // A generated order_number must be present (the column is NOT NULL).
    expect(typeof body!.order_number).toBe('string');
    expect((body!.order_number as string).length).toBeGreaterThan(0);
    // Real schema fields, not the phantom ones.
    expect(body!.supplier_id).toBe(1);
    expect(body!.items_json).toBeTypeOf('string');
    expect(body!.items).toBeUndefined();
    expect(body!.items_count).toBeUndefined();
    expect(body!.supplier_name).toBeUndefined();
    expect(body!.order_date).toBeUndefined();

    // Lines persist in items_json and carry product_id (delivered for #37 receive).
    const lines = JSON.parse(body!.items_json as string) as Array<{ product_id: number; quantity: number }>;
    expect(lines).toHaveLength(1);
    expect(lines[0].product_id).toBe(7);
    expect(lines[0].quantity).toBeGreaterThan(0);
  });
});
