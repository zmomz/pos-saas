import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import OrderTicket from './OrderTicket';

// M11 · FE-Platform a11y (#226) — native inputs → shadcn on the ticket modifier
// picker. The picker rendered raw <input type="radio|checkbox">; the design-system
// audit calls for the shadcn Checkbox / RadioGroup primitives (Radix roots) so the
// picker inherits the shared focus-ring, hit-target, keyboard model and disabled
// styling instead of bare browser defaults. Radix renders these as <button> with
// role="checkbox"/"radio" (native inputs are <input>), so the tag distinguishes
// them; behaviour (toggle / single-select) must survive the swap.

const BASE = 'http://127.0.0.1:8000';
const TID = 7;
const PID = 42;

const TICKET = { id: TID, table_id: 1, order_type: 'dine_in', status: 'open' };

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

async function openPickerForProduct() {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const addBtn = await screen.findByRole('button', { name: /add item/i });
  await user.click(addBtn);
  const dialog = within(await screen.findByRole('dialog'));
  const productSelect = dialog.getAllByRole('combobox')[0];
  await user.click(productSelect);
  const option = await screen.findByRole('option', { name: /latte/i });
  await user.click(option);
  return { dialog, user };
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('OrderTicket modifier picker — shadcn primitives (#226)', () => {
  it('renders multi-select options as shadcn Checkbox primitives that toggle', async () => {
    server.use(...baseHandlers());
    renderPage();
    const { dialog, user } = await openPickerForProduct();

    const cheese = await dialog.findByRole('checkbox', { name: /cheese/i });
    // Radix Checkbox is a <button role="checkbox">, not a native <input>.
    expect(cheese.tagName).toBe('BUTTON');
    expect(cheese).toHaveAttribute('aria-checked', 'false');

    await user.click(cheese);
    await waitFor(() => expect(cheese).toHaveAttribute('aria-checked', 'true'));
  });

  it('renders single-select options as shadcn radios enforcing one pick', async () => {
    server.use(...baseHandlers());
    renderPage();
    const { dialog, user } = await openPickerForProduct();

    const small = await dialog.findByRole('radio', { name: /small/i });
    const large = await dialog.findByRole('radio', { name: /large/i });
    // Radix RadioGroupItem is a <button role="radio">, not a native <input>.
    expect(small.tagName).toBe('BUTTON');
    expect(large.tagName).toBe('BUTTON');

    await user.click(small);
    await waitFor(() => expect(small).toHaveAttribute('aria-checked', 'true'));

    // Single-select: picking Large releases Small (only one selection survives).
    await user.click(large);
    await waitFor(() => expect(large).toHaveAttribute('aria-checked', 'true'));
    expect(small).toHaveAttribute('aria-checked', 'false');
  });
});
