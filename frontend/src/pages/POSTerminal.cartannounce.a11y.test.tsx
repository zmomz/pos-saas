import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the core cashier flow.
//
// Activating a product tile adds the item to the cart, but that result was
// SILENT to a screen reader: only barcode scans set a message, and even that
// message div is not a live region. A non-sighted (or keyboard-only-with-SR)
// cashier who tabs onto a product and presses Enter hears nothing back and has
// no confirmation the item landed in the cart — WCAG 4.1.3 (status messages).
//
// This slice wires a persistent polite live region into `addToCart`, so every
// cart addition (tile tap, keyboard activation, or scan) is announced by name.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

function mountSideHandlers(products: unknown[] = []) {
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
    http.get(PRODUCTS_URL, () => HttpResponse.json(products)),
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

const WIDGET = { id: 1, name: 'Widget', price: 5, category: 'General' };

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal cart-add screen-reader announcements (#226)', () => {
  it('mounts a polite, atomic live region that is silent on first paint', async () => {
    server.use(...mountSideHandlers([WIDGET]));
    renderPage();

    // The product tile confirms the page is ready.
    await screen.findByRole('button', { name: /widget/i });

    const region = screen.getByTestId('cart-announcer');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveAttribute('aria-atomic', 'true');
    expect(region).toHaveClass('sr-only');
    expect(region).toHaveTextContent('');
  });

  it('announces the item by name when a product tile is activated', async () => {
    server.use(...mountSideHandlers([WIDGET]));
    renderPage();

    const tile = await screen.findByRole('button', { name: /widget/i });
    await userEvent.click(tile);

    const region = screen.getByTestId('cart-announcer');
    expect(region).toHaveTextContent(/widget/i);
    expect(region).toHaveTextContent(/added/i);
  });
});
