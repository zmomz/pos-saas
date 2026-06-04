import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import {
  createTransaction,
  issueGiftCard,
  getGiftCardBalance,
} from './api';

// CRM-03 / PRC-05 (F-038): lock the gift-card API surface — the wrappers the page
// uses to issue/look-up a card, and the single-tender gift-card code the POS
// checkout must forward so the backend can validate + decrement it on the sale.
const BASE = 'http://127.0.0.1:8000';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('gift card api wrappers', () => {
  it('issueGiftCard posts the amount and returns the issued card', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/gift-cards`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 9,
          code: 'GC-ABCDEF123456',
          currency: 'SAR',
          initial_balance: 200,
          balance: 200,
          status: 'active',
        });
      })
    );

    const card = await issueGiftCard({ amount: 200 });
    expect(body!.amount).toBe(200);
    expect(card.code).toBe('GC-ABCDEF123456');
    expect(card.balance).toBe(200);
  });

  it('getGiftCardBalance reads the balance for a code', async () => {
    server.use(
      http.get(`${BASE}/api/v1/gift-cards/GC-XYZ/balance`, () =>
        HttpResponse.json({ code: 'GC-XYZ', balance: 75, status: 'active', is_redeemable: true })
      )
    );
    const res = await getGiftCardBalance('GC-XYZ');
    expect(res.balance).toBe(75);
    expect(res.is_redeemable).toBe(true);
  });

  it('createTransaction forwards a single-tender gift-card code (PRC-05)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/pos/transaction`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          invoice_number: 'INV-0001-000001',
          subtotal: 100,
          vat_amount: 15,
          total_amount: 115,
          payment_method: 'giftcard',
        });
      })
    );

    await createTransaction({
      items: [{ product_id: 5, name: 'Mug', quantity: 1, price: 100, vat_rate: 0.15 }],
      payment_method: 'giftcard',
      payment_gift_card_code: 'GC-ABCDEF123456',
    });

    expect(captured!.payment_method).toBe('giftcard');
    expect(captured!.payment_gift_card_code).toBe('GC-ABCDEF123456');
  });
});
