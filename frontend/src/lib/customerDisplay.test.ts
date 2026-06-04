// F-047 (HW-05 / UX-07): the customer-display payload must carry each line's
// Arabic name (bilingual, RTL) and the merchant brand name (white-label). Before
// this fix the POS writer emitted only `{name, quantity, price}` and no business
// name, so the second screen rendered English-only and showed a hardcoded
// platform header.
import { describe, it, expect } from 'vitest';
import {
  buildCustomerDisplayPayload,
  paidCustomerDisplayPayload,
  CUSTOMER_DISPLAY_KEY,
} from './customerDisplay';

describe('buildCustomerDisplayPayload (HW-05 display-sync contract)', () => {
  it('carries name_ar per line and the businessName when set', () => {
    const payload = buildCustomerDisplayPayload(
      [{ name: 'Latte', name_ar: 'لاتيه', quantity: 2, price: 12 }],
      { subtotal: 24, vat: 3.6, total: 27.6 },
      'مقهى الرياض',
    );

    expect(payload.items[0].name_ar).toBe('لاتيه');
    expect(payload.items[0].name).toBe('Latte');
    expect(payload.businessName).toBe('مقهى الرياض');
    expect(payload.status).toBe('active');
    expect(payload.subtotal).toBe(24);
    expect(payload.vat).toBe(3.6);
    expect(payload.total).toBe(27.6);
  });

  it('omits name_ar when a line has none (so the reader falls back to name)', () => {
    const payload = buildCustomerDisplayPayload(
      [{ name: 'Water', quantity: 1, price: 2 }],
      { subtotal: 2, vat: 0.3, total: 2.3 },
      'Acme',
    );
    expect('name_ar' in payload.items[0]).toBe(false);
  });

  it('omits businessName when unknown (reader keeps its own default)', () => {
    const payload = buildCustomerDisplayPayload(
      [{ name: 'Water', name_ar: 'ماء', quantity: 1, price: 2 }],
      { subtotal: 2, vat: 0.3, total: 2.3 },
      '',
    );
    expect('businessName' in payload).toBe(false);
  });

  it('reports an idle status for an empty cart', () => {
    const payload = buildCustomerDisplayPayload([], { subtotal: 0, vat: 0, total: 0 }, 'Acme');
    expect(payload.status).toBe('idle');
    expect(payload.items).toEqual([]);
  });
});

describe('paidCustomerDisplayPayload (thank-you state stays branded)', () => {
  it('is paid + empty and keeps the brand name when set', () => {
    const payload = paidCustomerDisplayPayload('مقهى الرياض');
    expect(payload.status).toBe('paid');
    expect(payload.items).toEqual([]);
    expect(payload.businessName).toBe('مقهى الرياض');
  });

  it('omits businessName when unknown', () => {
    expect('businessName' in paidCustomerDisplayPayload('')).toBe(false);
  });
});

describe('CUSTOMER_DISPLAY_KEY', () => {
  it('is the shared localStorage channel both the writer and reader use', () => {
    expect(CUSTOMER_DISPLAY_KEY).toBe('pos-customer-display');
  });
});
