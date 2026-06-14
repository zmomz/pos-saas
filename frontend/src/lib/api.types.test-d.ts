// ISSUE-026 — Typed API return signatures on drift-prone endpoints.
//
// Contract type-tests for the five endpoints whose response-shape drift silently
// zeroed a UI (#21…#25). Each block asserts the explicit return signature (AC1)
// and that the *wrong* key that caused the original drift is absent — reading it
// off the typed response is a compile error (AC2). The `.not.toHaveProperty`
// guard fails the type-check if a drift field is ever re-introduced to the type.
// Run via `pnpm run typecheck` (Vitest typecheck mode).
import { test, expectTypeOf } from 'vitest';
import {
  getProductsList,
  getExpenses,
  getAgentClients,
  getPackages,
  getDiscounts,
} from './api';

// #21 (H6): ProductManagement read `data.products` → always []. The list is
// `{ items, total }`; there is no `products` key.
test('getProductsList returns { items, total } — not `products`', async () => {
  const data = await getProductsList();
  expectTypeOf(data.items).toBeArray();
  expectTypeOf(data.total).toBeNumber();
  expectTypeOf(data).not.toHaveProperty('products');
});

// #22: ExpenseTracking must read `items` off the entity list response. The list
// is `{ items, total }`; there is no `expenses` key.
test('getExpenses returns { items, total } — not `expenses`', async () => {
  const data = await getExpenses();
  expectTypeOf(data.items).toBeArray();
  expectTypeOf(data.total).toBeNumber();
  expectTypeOf(data).not.toHaveProperty('expenses');
});

// #23 (H9): the Remaining-Slots tile must come from `remaining_slots`/`total` on
// the clients response — not from `client_slots`/`used_slots`, which live on the
// branding payload and were the source of the always-`0` tile.
test('getAgentClients exposes remaining_slots/total — not client_slots', async () => {
  const data = await getAgentClients();
  expectTypeOf(data.items).toBeArray();
  expectTypeOf(data.total).toBeNumber();
  expectTypeOf(data.remaining_slots).toBeNumber();
  expectTypeOf(data).not.toHaveProperty('client_slots');
});

// #24 (U1.1): the package retail-price line must read `suggested_retail_price`;
// the never-emitted `retail_price_per_client` rendered the figure as 0.00 SAR.
test('getPackages items carry suggested_retail_price — not retail_price_per_client', async () => {
  const data = await getPackages();
  expectTypeOf(data.items).toBeArray();
  expectTypeOf(data.total).toBeNumber();
  const pkg = data.items[0];
  expectTypeOf(pkg.suggested_retail_price).toEqualTypeOf<number | null | undefined>();
  expectTypeOf(pkg).not.toHaveProperty('retail_price_per_client');
});

// #25 (U3.5): the discounts list rows carry `usage_count`; the "Total Uses"
// rollup that summed the never-emitted `used_count` always rendered 0.
test('getDiscounts rows carry usage_count — not used_count', async () => {
  const data = await getDiscounts();
  expectTypeOf(data.items).toBeArray();
  expectTypeOf(data.total).toBeNumber();
  const row = data.items[0];
  expectTypeOf(row.usage_count).toEqualTypeOf<number | null | undefined>();
  expectTypeOf(row).not.toHaveProperty('used_count');
});
