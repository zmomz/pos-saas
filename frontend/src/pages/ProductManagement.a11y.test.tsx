import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// ISSUE-226 (M11 FE-Platform · a11y) — the "Add/Edit product" form renders a
// *visible* <Label> above each text/number field, but the Labels were never
// programmatically associated with their <Input> (no htmlFor/id, no aria-label).
// A sighted user reads "Price" above the box, but a screen-reader user tabbing
// into the field heard only "edit text" — WCAG 1.3.1 (info & relationships) /
// 3.3.2 (labels or instructions). Each field must expose its accessible name so
// getByLabelText can reach it.

const BASE = 'http://127.0.0.1:8000';

const PRODUCTS = { items: [], total: 0 };

function mockEndpoints() {
  server.use(
    http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(PRODUCTS)),
    http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/entities/categories`, () =>
      HttpResponse.json({ items: [], total: 0 })
    )
  );
}

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

describe('ProductManagement form field labelling (ISSUE-226 a11y)', () => {
  // The labels carry a trailing " *" on required fields, so match by prefix.
  const LABELLED_FIELDS = ['Name', 'Arabic Name', 'Barcode', 'Price', 'Quantity'];

  it('exposes each product-form field by its visible label as accessible name', async () => {
    mockEndpoints();
    renderPage();

    // Open the "Add New Product" dialog.
    await userEvent.click(
      await screen.findByRole('button', { name: /add product/i })
    );
    // The dialog form is present once its heading renders.
    await screen.findByText('Add New Product');

    for (const field of LABELLED_FIELDS) {
      const input = screen.getByLabelText(new RegExp(`^${field}`, 'i'));
      expect(input.tagName).toBe('INPUT');
    }
  });
});
