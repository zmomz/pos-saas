import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the POS terminal's
// single-select button groups.
//
// The category chips, the payment-method tiles and the split-payment toggle each
// signalled their ACTIVE / SELECTED member with colour classes only (a brand
// border + tinted background). A screen-reader user tabbing the group heard each
// option's label but never WHICH one was currently selected — WCAG 1.4.1
// (use-of-colour) / 4.1.2 (name, role, value). This slice exposes the selected
// member programmatically via `aria-pressed`, matching the price-check toggle's
// existing convention.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

const PRODUCTS = [
  { id: 1, name: 'Latte', price: 15, category: 'Drinks' },
  { id: 2, name: 'Burger', price: 30, category: 'Food' },
];

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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal selected-state a11y (#226)', () => {
  it('exposes the selected payment method via aria-pressed', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    // Cash is the default tender: it must be programmatically pressed, and the
    // other tenders un-pressed — not merely colour-tinted.
    const cash = await screen.findByRole('button', { name: /^cash$/i });
    const card = screen.getByRole('button', { name: /^card$/i });
    expect(cash).toHaveAttribute('aria-pressed', 'true');
    expect(card).toHaveAttribute('aria-pressed', 'false');

    // Selecting another tender moves the pressed state with it.
    await userEvent.click(card);
    expect(card).toHaveAttribute('aria-pressed', 'true');
    expect(cash).toHaveAttribute('aria-pressed', 'false');
  });

  it('exposes the active category chip via aria-pressed', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    // "All" is the default filter; the per-category chips are un-pressed.
    const all = await screen.findByRole('button', { name: /^all$/i });
    const drinks = await screen.findByRole('button', { name: /^drinks$/i });
    expect(all).toHaveAttribute('aria-pressed', 'true');
    expect(drinks).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(drinks);
    expect(drinks).toHaveAttribute('aria-pressed', 'true');
    expect(all).toHaveAttribute('aria-pressed', 'false');
  });

  it('exposes the split-payment toggle state via aria-pressed', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    const split = await screen.findByRole('button', { name: /^split$/i });
    expect(split).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(split);
    await waitFor(() => expect(split).toHaveAttribute('aria-pressed', 'true'));
  });
});
