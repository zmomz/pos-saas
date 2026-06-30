import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { resolveBranchTaxRate, setBranchTaxRate } from './api';

// #220 (M4·Inventory multi-branch: branch-level tax) — thin client bindings over
// the per-branch VAT-rate-override endpoints (/pos/branches/{id}/tax-rate).

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('branch tax API bindings (#220)', () => {
  it('setBranchTaxRate PUTs the override and returns the saved rate', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/pos/branches/7/tax-rate`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ branch_id: 7, vat_rate: 5, is_override: true });
      })
    );

    const saved = await setBranchTaxRate(7, 5);
    expect(body).toEqual({ vat_rate: 5 });
    expect(saved.vat_rate).toBe(5);
    expect(saved.is_override).toBe(true);
  });

  it('resolveBranchTaxRate returns the effective rate and override flag', async () => {
    server.use(
      http.get(`${BASE}/pos/branches/7/tax-rate`, () =>
        HttpResponse.json({ branch_id: 7, vat_rate: 15, is_override: false })
      )
    );

    const resolved = await resolveBranchTaxRate(7);
    expect(resolved.vat_rate).toBe(15);
    expect(resolved.is_override).toBe(false);
  });
});
