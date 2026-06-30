import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { resolveBranchPromotions, setBranchPromotion } from './api';

// #220 (M4·Inventory multi-branch: branch-level promotions) — thin client
// bindings over the per-branch promotion opt-out endpoints
// (/pos/branches/{id}/promotions).

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('branch promotions API bindings (#220)', () => {
  it('resolveBranchPromotions returns effective promos and disabled ids', async () => {
    server.use(
      http.get(`${BASE}/pos/branches/7/promotions/resolve`, () =>
        HttpResponse.json({
          branch_id: 7,
          promotions: [{ promotion_id: 2, name: 'Drinks 10%', kind: 'category' }],
          disabled_promotion_ids: [1],
        }),
      ),
    );

    const resolved = await resolveBranchPromotions(7);
    expect(resolved.promotions.map((p) => p.promotion_id)).toEqual([2]);
    expect(resolved.disabled_promotion_ids).toEqual([1]);
  });

  it('setBranchPromotion PUTs the enablement flag', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/pos/branches/7/promotions/1`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ branch_id: 7, promotion_id: 1, is_enabled: false });
      }),
    );

    const saved = await setBranchPromotion(7, 1, false);
    expect(body).toEqual({ is_enabled: false });
    expect(saved.is_enabled).toBe(false);
  });
});
