import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the ticket modifier picker.
//
// Each modifier group renders a visible name ("Size") and, when required, a
// "Required" badge — but the group container carried NO group semantics. A
// screen-reader user tabbing the native radios/checkboxes heard each option's
// label but never WHICH group it belonged to, nor that a single-select group is
// a radio group, nor that it is required. This slice exposes each group as a
// programmatic `group`/`radiogroup` labelled by its name, with `aria-required`
// on required single-select groups.

const BASE = 'http://127.0.0.1:8000';
const TID = 7;
const PID = 42;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };

// A single-select REQUIRED group (radios) and a multi-select optional group
// (checkboxes) — the two shapes the picker renders.
const GROUPS = {
  items: [
    {
      id: 11,
      name: 'Size',
      required: true,
      max_select: 1,
      modifiers: [
        { id: 101, group_id: 11, name: 'Small', price_delta: 0 },
        { id: 102, group_id: 11, name: 'Large', price_delta: 3 },
      ],
    },
    {
      id: 12,
      name: 'Extras',
      required: false,
      max_select: 3,
      modifiers: [
        { id: 201, group_id: 12, name: 'Cheese', price_delta: 2 },
        { id: 202, group_id: 12, name: 'Bacon', price_delta: 4 },
      ],
    },
  ],
  total: 2,
};

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}`, () => HttpResponse.json(TICKET)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/items`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/check`, () => HttpResponse.json(null)),
    http.get(`${BASE}/api/v1/restaurant/order-tickets/${TID}/print-routing`, () =>
      HttpResponse.json(null)
    ),
    http.get(`${BASE}/api/v1/restaurant/order-tickets`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/restaurant/tables`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/restaurant/combos`, () => HttpResponse.json([])),
    // getProducts() reads client.entities.products.query → raw array body.
    http.get(`${BASE}/api/v1/entities/products`, () =>
      HttpResponse.json([{ id: PID, name: 'Latte', price: 15 }])
    ),
    http.get(`${BASE}/api/v1/restaurant/products/${PID}/modifier-groups`, () =>
      HttpResponse.json(GROUPS)
    ),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/restaurant/tickets/${TID}`]}>
      <LanguageProvider>
        <Routes>
          <Route path="/restaurant/tickets/:ticketId" element={<OrderTicket />} />
        </Routes>
      </LanguageProvider>
    </MemoryRouter>
  );
}

// Open the add-item dialog and pick the product so the modifier picker renders.
async function openPickerForProduct() {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const addBtn = await screen.findByRole('button', { name: /add item/i });
  await user.click(addBtn);
  const dialog = within(await screen.findByRole('dialog'));
  // The product select is the first combobox in the dialog.
  const productSelect = dialog.getAllByRole('combobox')[0];
  await user.click(productSelect);
  const option = await screen.findByRole('option', { name: /latte/i });
  await user.click(option);
  return dialog;
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('OrderTicket modifier picker — screen-reader group semantics (#226)', () => {
  it('exposes a required single-select group as a named, required radiogroup', async () => {
    server.use(...baseHandlers());
    renderPage();
    const dialog = await openPickerForProduct();

    const sizeGroup = await dialog.findByRole('radiogroup', { name: /size/i });
    expect(sizeGroup).toHaveAttribute('aria-required', 'true');
  });

  it('exposes an optional multi-select group as a named group', async () => {
    server.use(...baseHandlers());
    renderPage();
    const dialog = await openPickerForProduct();

    // Present and named by its heading — not falsely marked required.
    const extras = await dialog.findByRole('group', { name: /extras/i });
    await waitFor(() => expect(extras).not.toHaveAttribute('aria-required', 'true'));
  });
});
