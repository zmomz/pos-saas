import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the POS checkout.
//
// Once a discount code is applied, the summary shows a compact chip with an
// icon-only "X" button that clears it. That button carried no text and no
// aria-label, so a screen-reader user tabbing the checkout heard only "button"
// with no hint that it removes the applied discount — WCAG 4.1.2 (name, role,
// value). Its sibling "clear tip" control already exposes an aria-label; this
// slice brings the remove-discount button to the same bar and localizes it.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

const PRODUCTS = [{ id: 1, name: 'Latte', price: 15, category: 'Drinks' }];

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
    http.get(PRODUCTS_URL, () => HttpResponse.json(PRODUCTS)),
    http.post(`${BASE}/entities/discounts/validate`, () =>
      HttpResponse.json({ valid: true, code: 'SAVE10', type: 'percentage', value: 10, discount_amount: 1.5 })
    ),
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

async function applyDiscount(locale: { code: RegExp; apply: RegExp | string } = { code: /enter code/i, apply: /^apply$/i }) {
  // Ring up an item so there is a subtotal to discount, then apply a code.
  const latte = await screen.findByRole('button', { name: /latte/i });
  await userEvent.click(latte);
  const input = screen.getByPlaceholderText(locale.code);
  await userEvent.type(input, 'SAVE10');
  await userEvent.click(screen.getByRole('button', { name: locale.apply }));
  await screen.findByText(/SAVE10/);
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal remove-discount a11y (#226)', () => {
  it('names the remove-discount button for screen readers', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await applyDiscount();

    // The icon-only clear button must be reachable by its accessible name.
    const remove = screen.getByRole('button', { name: /remove discount/i });
    expect(remove).toBeInTheDocument();
  });

  it('actually clears the applied discount when activated', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await applyDiscount();

    await userEvent.click(screen.getByRole('button', { name: /remove discount/i }));
    // The chip disappears; the code entry input returns.
    await waitFor(() => expect(screen.queryByText(/SAVE10/)).not.toBeInTheDocument());
    expect(screen.getByPlaceholderText(/enter code/i)).toBeInTheDocument();
  });

  it('localizes the remove-discount name in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(...mountSideHandlers());
    renderPage();
    await applyDiscount({ code: /أدخل الكود/, apply: 'تطبيق' });

    expect(screen.getByRole('button', { name: 'إزالة الخصم' })).toBeInTheDocument();
    localStorage.removeItem('pos-language');
  });
});
