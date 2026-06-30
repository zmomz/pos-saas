import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { getBranchPrices, setBranchPrice, resolveBranchPrice } from './api';

// #220 (M4·Inventory multi-branch: branch-level pricing) — thin client bindings
// over the per-branch price-override endpoints (/pos/branches/{id}/prices).

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('branch pricing API bindings (#220)', () => {
  it('setBranchPrice PUTs the override and getBranchPrices lists it', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/pos/branches/7/prices`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ branch_id: 7, product_id: 3, price: 14.5 });
      }),
      http.get(`${BASE}/pos/branches/7/prices`, () =>
        HttpResponse.json({
          branch_id: 7,
          items: [{ product_id: 3, price: 14.5 }],
          total: 1,
        })
      )
    );

    const saved = await setBranchPrice(7, 3, 14.5);
    expect(body).toEqual({ product_id: 3, price: 14.5 });
    expect(saved.price).toBe(14.5);

    const listing = await getBranchPrices(7);
    expect(listing.items).toEqual([{ product_id: 3, price: 14.5 }]);
  });

  it('resolveBranchPrice returns the effective price and override flag', async () => {
    server.use(
      http.get(`${BASE}/pos/branches/7/prices/resolve`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get('product_id')).toBe('3');
        return HttpResponse.json({
          product_id: 3,
          branch_id: 7,
          price: 14.5,
          is_override: true,
        });
      })
    );

    const resolved = await resolveBranchPrice(7, 3);
    expect(resolved.price).toBe(14.5);
    expect(resolved.is_override).toBe(true);
  });
});
