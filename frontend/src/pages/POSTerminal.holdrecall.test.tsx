import { describe, it, expect } from 'vitest';
import { holdLineFromCart, cartLineFromHeld, type CartItem } from './POSTerminal';

// ISSUE-031 (H28): hold→recall dropped `variant_id` and the open price, so a recalled
// variant SKU collapsed to its parent product (parent stock deducted, variant siblings
// merged, open price reverted to catalog). These tests pin the serialization round-trip
// — hold a cart line, recall it — through the two pure helpers the handlers use.

// A variant line: `product.id` is the PARENT product id; `product.price` carries the
// variant's price; `variantId` identifies the SKU. (As built by lookupAndAdd.)
function variantLine(): CartItem {
  return {
    product: { id: 7, name: 'T-Shirt', name_ar: 'قميص', price: 50 },
    quantity: 2,
    variantId: 99,
    key: 'v99',
  };
}

describe('ISSUE-031 hold→recall preserves the variant SKU', () => {
  it('restores variant_id, the variant price, and a distinct variant cart key', () => {
    const held = holdLineFromCart(variantLine());
    const restored = cartLineFromHeld(held, []);

    expect(restored.variantId).toBe(99);
    // The recalled line keeps the variant's price (not the parent catalog price).
    expect(restored.product.price).toBe(50);
    // The cart key is variant-scoped (`v99`), so it never collapses onto the parent.
    expect(restored.key).toBe('v99');
  });

  it('keeps two variants of one product as separate lines (distinct keys)', () => {
    const small: CartItem = {
      product: { id: 7, name: 'T-Shirt — S', price: 50 },
      quantity: 1,
      variantId: 99,
      key: 'v99',
    };
    const large: CartItem = {
      product: { id: 7, name: 'T-Shirt — L', price: 55 },
      quantity: 1,
      variantId: 100,
      key: 'v100',
    };

    const a = cartLineFromHeld(holdLineFromCart(small), []);
    const b = cartLineFromHeld(holdLineFromCart(large), []);

    // Same parent product (id 7) but the keys stay distinct, so they never merge.
    expect(a.key).not.toBe(b.key);
    expect(a.variantId).toBe(99);
    expect(b.variantId).toBe(100);
  });

  it('restores an open-price line at the cashier-entered price, not catalog', () => {
    // POS-11: an open-price product. Catalog default is 10; the cashier sold it at 42.
    const catalog: Product = { id: 3, name: 'Bulk Coffee', price: 10, is_open_price: true };
    const line: CartItem = {
      product: catalog,
      quantity: 1,
      unitPrice: 42,
      key: 'p3',
    };

    // Recall against the live catalog (price still 10) — the entered price must survive.
    const restored = cartLineFromHeld(holdLineFromCart(line), [catalog]);

    expect(restored.unitPrice).toBe(42);
  });
});
