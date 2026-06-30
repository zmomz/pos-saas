import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { getCrossBranchSales } from './api';

// #220 (M4·Inventory multi-branch: cross-branch reporting) — thin client binding
// over /pos/reports/cross-branch-sales, which rolls each branch's net sales and
// sale count up side by side for the chain.

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('cross-branch reporting API binding (#220)', () => {
  it('getCrossBranchSales returns the per-branch summary and totals', async () => {
    server.use(
      http.get(`${BASE}/pos/reports/cross-branch-sales`, () =>
        HttpResponse.json({
          branches: [
            { branch_id: 1, branch_name: 'Airport', net_sales: 150.0, sales_count: 2 },
            { branch_id: 2, branch_name: 'Suburb', net_sales: 25.0, sales_count: 1 },
          ],
          total_net_sales: 175.0,
          total_sales_count: 3,
        })
      )
    );

    const summary = await getCrossBranchSales();
    expect(summary.branches).toHaveLength(2);
    expect(summary.branches[0].branch_name).toBe('Airport');
    expect(summary.total_net_sales).toBe(175.0);
    expect(summary.total_sales_count).toBe(3);
  });

  it('getCrossBranchSales forwards the start/end window', async () => {
    let url: URL | null = null;
    server.use(
      http.get(`${BASE}/pos/reports/cross-branch-sales`, ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json({ branches: [], total_net_sales: 0, total_sales_count: 0 });
      })
    );

    await getCrossBranchSales('2026-01-15T00:00:00', '2026-01-25T00:00:00');
    expect(url!.searchParams.get('start')).toBe('2026-01-15T00:00:00');
    expect(url!.searchParams.get('end')).toBe('2026-01-25T00:00:00');
  });
});
