import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#276) — end-to-end keyboard-only checkout walkthrough.
//
// The per-control POS a11y tests (#226) each pin one widget (named pickers, cart
// announcements, steppers). None drives a WHOLE checkout with the keyboard alone,
// so a break in the item → cart → pay → settle chain — a tile not reachable by
// Tab, a "sale complete" screen that swaps in silently — could slip through.
//
// This walkthrough drives a full cash sale using only Tab + Enter and asserts, at
// each step, that focus reaches the control and that the result is announced to a
// screen reader:
//   • item → cart:  Tab reaches the product tile; Enter adds it; the polite
//                   cart-announcer names the added item (WCAG 4.1.3).
//   • pay → settle: Tab reaches the Pay CTA; Enter settles the sale; focus moves
//                   to the "sale complete" confirmation so an SR user — who would
//                   otherwise hear nothing when the view swaps to the receipt —
//                   is told the sale went through (WCAG 2.4.3 Focus Order).

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

const JUICE = { id: 1, name: 'Juice', price: 12, vat_rate: 0.15, category: 'General' };

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(PRODUCTS_URL, () => HttpResponse.json([JUICE])),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json({ items: [] })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

// Tab from the current focus until it lands on `target`, without ever using the
// pointer. A bounded loop keeps the assertion resilient to controls that precede
// the target while still proving it is genuinely in the keyboard tab order.
async function tabTo(user: ReturnType<typeof userEvent.setup>, target: Element, max = 100) {
  for (let i = 0; i < max && document.activeElement !== target; i++) {
    await user.tab();
  }
}

beforeAll(() => {
  localStorage.setItem('pos-language', 'en');
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  localStorage.clear();
  server.close();
});

describe('POSTerminal keyboard-only checkout walkthrough (#276)', () => {
  it('completes item → cart → pay → settle with the keyboard, announcing and moving focus', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/pos/transaction`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          invoice_number: 'INV-1',
          total_amount: 13.8,
          vat_amount: 1.8,
          subtotal: 12,
          payment_method: 'cash',
        });
      }),
      ...mountSideHandlers()
    );

    const user = userEvent.setup();
    renderPage();

    // ── item → cart ────────────────────────────────────────────────────────
    const tile = await screen.findByRole('button', { name: /juice/i });
    await tabTo(user, tile);
    expect(document.activeElement).toBe(tile); // reachable by Tab, no pointer

    await user.keyboard('{Enter}'); // activate the tile with the keyboard

    // The addition is announced to a screen reader by name.
    const announcer = screen.getByTestId('cart-announcer');
    await waitFor(() => expect(announcer).toHaveTextContent(/juice/i));
    expect(announcer).toHaveTextContent(/added/i);

    // ── pay → settle ───────────────────────────────────────────────────────
    const pay = screen.getByRole('button', { name: /^pay\b/i });
    await tabTo(user, pay);
    expect(document.activeElement).toBe(pay); // CTA reachable by Tab

    await user.keyboard('{Enter}'); // settle with the keyboard

    // The sale is settled…
    await waitFor(() => expect(posted).not.toBeNull());
    await screen.findByText(/INV-1/);

    // …and focus moves to the "sale complete" confirmation, so an SR user is
    // told the view changed and the sale went through.
    const done = screen.getByText(/تمت العملية بنجاح/);
    await waitFor(() => expect(document.activeElement).toBe(done));
  });
});
