import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the POS checkout.
//
// The discount-code and tip fields in the totals/checkout column each had a
// *visible* <label> that was never programmatically associated with its
// <input> (no htmlFor/id, no aria-label). A sighted cashier reads "Discount
// code" / "Tip" above the box, but a screen-reader user tabbing into the field
// heard only "edit text" — WCAG 1.3.1 (info & relationships) and 3.3.2 (labels
// or instructions). This slice associates each label with its control so the
// accessible name is announced (verified via getByLabelText).

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

async function ringUpLatte() {
  const latte = await screen.findByRole('button', { name: /latte/i });
  await userEvent.click(latte);
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal checkout inputs a11y (#226)', () => {
  it('associates the discount-code label with its input', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await ringUpLatte();

    const input = screen.getByLabelText(/discount code/i);
    expect(input.tagName).toBe('INPUT');
  });

  it('associates the tip label with its input', async () => {
    server.use(...mountSideHandlers());
    renderPage();
    await ringUpLatte();

    const input = screen.getByLabelText(/^tip$/i);
    expect(input.tagName).toBe('INPUT');
  });
});
