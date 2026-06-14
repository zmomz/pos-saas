import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// ISSUE-038 (H7) — product↔category linkage. The product form's category Select
// is sourced from the merchant's category tree (getCategories), not a hardcoded
// array, and creating a product posts the chosen category's id as `category_id`.

const BASE = 'http://127.0.0.1:8000';
const CATEGORIES_URL = `${BASE}/api/v1/entities/categories`;
const PRODUCTS_URL = `${BASE}/api/v1/products/list`;
const CREATE_URL = `${BASE}/api/v1/products/create`;
const SUGGESTIONS_URL = `${BASE}/api/v1/products/reorder-suggestions`;

const CATEGORIES = {
  items: [
    { id: 1, user_id: 'u1', name: 'Beverages' },
    { id: 2, user_id: 'u1', name: 'Snacks' },
  ],
  total: 2,
  skip: 0,
  limit: 200,
};

const EMPTY_LIST = { items: [], total: 0 };

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ProductManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ProductManagement category linkage (ISSUE-038)', () => {
  it('sources the category Select from getCategories and posts the chosen category_id', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.get(CATEGORIES_URL, () => HttpResponse.json(CATEGORIES)),
      http.get(PRODUCTS_URL, () => HttpResponse.json(EMPTY_LIST)),
      http.get(SUGGESTIONS_URL, () => HttpResponse.json(EMPTY_LIST)),
      http.post(CREATE_URL, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 99, ...posted });
      })
    );

    renderPage();

    // Open the Add Product dialog.
    await userEvent.click(await screen.findByRole('button', { name: /add product/i }));

    // Fill the required fields.
    await userEvent.type(screen.getByPlaceholderText('Product name'), 'Cola');
    const dialog = screen.getByRole('dialog');
    const numbers = dialog.querySelectorAll('input[type="number"]');
    await userEvent.type(numbers[0] as HTMLElement, '5'); // price
    await userEvent.type(numbers[2] as HTMLElement, '10'); // quantity (after cost_price)

    // The category Select is sourced from the merchant's categories — pick one.
    // The dialog form has exactly one Select (the category picker).
    const trigger = within(dialog).getByRole('combobox');
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole('option', { name: 'Beverages' }));

    // Submit.
    const submit = screen
      .getAllByRole('button', { name: /^add product$/i })
      .pop() as HTMLElement;
    await userEvent.click(submit);

    expect(posted).not.toBeNull();
    expect(posted!.category_id).toBe(1);
  });
});
