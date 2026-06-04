// HW-05 / UX-07 (F-047): the contract for the customer-facing second screen.
//
// POSTerminal mirrors the live cart into the `pos-customer-display` localStorage
// key; CustomerDisplay.tsx polls it on a second screen. The writer previously
// emitted only `{name, quantity, price}` and no business name, so the display
// rendered items English-only and showed a hardcoded "POS System" header —
// breaking both RTL/Arabic (the cart line `name_ar`) and white-label (the
// merchant's brand) on the customer-facing screen.
//
// The payload builders below are pure so the display-sync contract is unit
// testable without rendering the whole POS terminal.

/** The localStorage key the POS terminal writes and the display screen reads. */
export const CUSTOMER_DISPLAY_KEY = 'pos-customer-display';

export interface CustomerDisplayItem {
  name: string;
  // HW-05: the Arabic name so the second screen renders the bilingual line
  // (`name_ar` primary, `name` secondary) instead of English-only.
  name_ar?: string;
  quantity: number;
  price: number;
}

export interface CustomerDisplayPayload {
  items: CustomerDisplayItem[];
  subtotal: number;
  vat: number;
  total: number;
  // HW-05 white-label: the merchant's brand name. Omitted when unknown so the
  // reader keeps its own default rather than blanking the header.
  businessName?: string;
  status: 'active' | 'paid' | 'idle';
}

/**
 * Build the live-cart payload for the customer display. Carries `name_ar` per
 * line (when set) and the merchant `businessName` (when set), so the second
 * screen is bilingual and branded.
 */
export function buildCustomerDisplayPayload(
  items: { name: string; name_ar?: string; quantity: number; price: number }[],
  totals: { subtotal: number; vat: number; total: number },
  businessName?: string,
): CustomerDisplayPayload {
  const payload: CustomerDisplayPayload = {
    items: items.map((it) => ({
      name: it.name,
      // Only carry name_ar when present so the key is absent (not undefined)
      // otherwise — the reader keys off its truthiness for the bilingual line.
      ...(it.name_ar ? { name_ar: it.name_ar } : {}),
      quantity: it.quantity,
      price: it.price,
    })),
    subtotal: totals.subtotal,
    vat: totals.vat,
    total: totals.total,
    status: items.length > 0 ? 'active' : 'idle',
  };
  if (businessName) payload.businessName = businessName;
  return payload;
}

/** The "thank you" / paid state, still branded with the merchant name when set. */
export function paidCustomerDisplayPayload(businessName?: string): CustomerDisplayPayload {
  const payload: CustomerDisplayPayload = {
    items: [],
    subtotal: 0,
    vat: 0,
    total: 0,
    status: 'paid',
  };
  if (businessName) payload.businessName = businessName;
  return payload;
}
