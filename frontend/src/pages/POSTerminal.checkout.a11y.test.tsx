import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the checkout controls.
//
// The loyalty/branch pickers are Radix Select triggers whose only name came from
// the visible placeholder *text* ("Select customer" / "Select branch"). That name
// disappears the moment a value is chosen: the trigger then announces just the
// value ("Sara"), with no indication of the field's purpose — a screen-reader
// user reviewing a filled ticket cannot tell which picker holds what. Likewise
// the redeem-points <input> carried only a `placeholder`, which is not an
// accessible name at all (WCAG 4.1.2 name/role/value; 3.3.2 labels).
//
// This slice gives each control a stable `aria-label` so its purpose is announced
// independent of its current value.

const BASE = 'http://127.0.0.1:8000/api/v1';

function checkoutHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () =>
      HttpResponse.json([{ id: 1, name: 'Sara' }])
    ),
    http.get(`${BASE}/entities/branches`, () =>
      HttpResponse.json([{ id: 2, name: 'Downtown' }])
    ),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/entities/products`, () => HttpResponse.json([])),
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

describe('POSTerminal checkout controls a11y (#226)', () => {
  it('keeps the customer picker announced by name after a customer is chosen', async () => {
    server.use(...checkoutHandlers());
    const user = userEvent.setup();
    renderPage();

    const customer = await screen.findByRole('combobox', { name: /select customer/i });
    await user.click(customer);
    await user.click(await screen.findByRole('option', { name: 'Sara' }));

    // Value is now "Sara"; the field must still be reachable by its purpose.
    expect(
      screen.getByRole('combobox', { name: /select customer/i })
    ).toBeInTheDocument();
  });

  it('keeps the branch picker announced by name after a branch is chosen', async () => {
    server.use(...checkoutHandlers());
    const user = userEvent.setup();
    renderPage();

    const branch = await screen.findByRole('combobox', { name: /select branch/i });
    await user.click(branch);
    await user.click(await screen.findByRole('option', { name: 'Downtown' }));

    expect(
      screen.getByRole('combobox', { name: /select branch/i })
    ).toBeInTheDocument();
  });

  it('gives the redeem-points input an accessible name', async () => {
    server.use(...checkoutHandlers());
    const user = userEvent.setup();
    renderPage();

    // The redeem field only appears once a named customer is selected.
    const customer = await screen.findByRole('combobox', { name: /select customer/i });
    await user.click(customer);
    await user.click(await screen.findByRole('option', { name: 'Sara' }));

    expect(
      await screen.findByRole('spinbutton', { name: /redeem points/i })
    ).toBeInTheDocument();
  });
});
