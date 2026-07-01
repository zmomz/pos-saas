import { describe, it, expect, vi } from 'vitest';
import { buildSearchGroups } from './globalSearchGroups';
import type { GlobalSearchResults } from '@/lib/api';

// #231 (Productivity — Global search UI): the cross-entity /search backend
// already returns products / customers / transactions. To surface it in the
// *global* ⌘K command palette (reachable from every page, not just /ops), each
// hit must become a navigable palette item. buildSearchGroups is the pure
// mapper from the API shape to CommandPalette groups; these tests pin the
// grouping, the labels, and — the point of making search "global" — that
// activating a hit navigates to the right entity page.

const t = (k: string) => k; // identity: assert on the i18n *keys* used

function results(over: Partial<GlobalSearchResults['results']> = {}): GlobalSearchResults {
  const r = {
    products: [] as GlobalSearchResults['results']['products'],
    customers: [] as GlobalSearchResults['results']['customers'],
    transactions: [] as GlobalSearchResults['results']['transactions'],
    ...over,
  };
  return { query: 'x', total_results: Object.values(r).reduce((n, a) => n + a.length, 0), results: r };
}

describe('buildSearchGroups (#231 global search → palette)', () => {
  it('maps each entity kind to its own labelled group', () => {
    const groups = buildSearchGroups(
      results({
        products: [{ id: 1, name: 'Widget', barcode: '123' }],
        customers: [{ id: 7, name: 'Sara', phone: '0555' }],
        transactions: [{ id: 9, invoice_number: 'INV-9', total_amount: 50 }],
      }),
      vi.fn(),
      t,
    );
    expect(groups.map((g) => g.label)).toEqual([
      'ops_search_products',
      'ops_search_customers',
      'ops_search_transactions',
    ]);
    // The product hit is named by the product.
    expect(groups[0].items[0].label).toMatch(/Widget/);
  });

  it('navigates to the entity page when a hit is activated', () => {
    const navigate = vi.fn();
    const groups = buildSearchGroups(
      results({
        products: [{ id: 1, name: 'Widget' }],
        customers: [{ id: 7, name: 'Sara' }],
        transactions: [{ id: 9, invoice_number: 'INV-9' }],
      }),
      navigate,
      t,
    );
    groups[0].items[0].onSelect?.(); // product
    groups[1].items[0].onSelect?.(); // customer
    groups[2].items[0].onSelect?.(); // transaction
    expect(navigate).toHaveBeenNthCalledWith(1, '/products');
    expect(navigate).toHaveBeenNthCalledWith(2, '/customers');
    expect(navigate).toHaveBeenNthCalledWith(3, '/ops');
  });

  it('omits empty entity kinds so no bare group renders', () => {
    const groups = buildSearchGroups(
      results({ customers: [{ id: 7, name: 'Sara' }] }),
      vi.fn(),
      t,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('ops_search_customers');
  });
});
