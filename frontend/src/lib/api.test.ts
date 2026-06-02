import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { createTransaction } from './api';

// T-F: assert the POS checkout payload the app actually sends — the layer where
// the discount / split-pay / loyalty / branch gaps historically hid.
const ENDPOINT = 'http://127.0.0.1:8000/api/v1/pos/transaction';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('createTransaction payload', () => {
  it('forwards discount, loyalty and branch fields to the backend', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post(ENDPOINT, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          invoice_number: 'INV-0001-000001',
          subtotal: 100,
          vat_amount: 15,
          total_amount: 115,
          payment_method: 'cash',
        });
      })
    );

    const result = await createTransaction({
      items: [{ product_id: 5, name: 'Cola', quantity: 2, price: 50, vat_rate: 0.15 }],
      payment_method: 'cash',
      discount_amount: 10,
      customer_id: 7,
      redeem_points: 100,
      branch_id: 3,
    });

    expect(result.invoice_number).toBe('INV-0001-000001');
    expect(captured).not.toBeNull();
    expect(captured!.discount_amount).toBe(10);
    expect(captured!.customer_id).toBe(7);
    expect(captured!.redeem_points).toBe(100);
    expect(captured!.branch_id).toBe(3);
    expect((captured!.items as unknown[]).length).toBe(1);
  });
});
