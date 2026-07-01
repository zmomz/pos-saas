import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the core cashier flow's
// item-entry inputs.
//
// The barcode-scan and product-search fields carried only a `placeholder`. A
// placeholder is NOT an accessible name (dom-accessibility-api ignores it, and
// real screen readers announce an unlabelled "edit text"), so a non-sighted
// cashier reaching either field by keyboard hears no purpose for it — WCAG
// 4.1.2 (name, role, value). This slice gives each field a stable `aria-label`
// so it is announced by name.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

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
    http.get(PRODUCTS_URL, () => HttpResponse.json([])),
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal search/scan a11y (#226)', () => {
  it('gives the barcode-scan field an accessible name', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    expect(
      await screen.findByRole('textbox', { name: /scan barcode/i })
    ).toBeInTheDocument();
  });

  it('gives the product-search field an accessible name', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    expect(
      await screen.findByRole('textbox', { name: /search products/i })
    ).toBeInTheDocument();
  });
});
