import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ProductManagement from './ProductManagement';

// ISSUE-068 — a soft-deleted (archived) product is hidden from the active
// catalog by default; toggling "show archived" surfaces it with a Restore
// control that POSTs to /products/{id}/restore and reloads.

const BASE = 'http://127.0.0.1:8000';

const ACTIVE = {
  items: [{ id: 1, name: 'Espresso', price: 10, quantity: 5, vat_rate: 15, is_active: true }],
  total: 1,
};
const WITH_ARCHIVED = {
  items: [
    { id: 1, name: 'Espresso', price: 10, quantity: 5, vat_rate: 15, is_active: true },
    { id: 2, name: 'Retired', price: 12, quantity: 0, vat_rate: 15, is_active: false },
  ],
  total: 2,
};

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

describe('ProductManagement archive/restore (ISSUE-068)', () => {
  it('toggling "show archived" surfaces an archived product and restores it', async () => {
    let restoreCalledFor: number | null = null;
    server.use(
      http.get(`${BASE}/api/v1/products/list`, ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json(
          url.searchParams.get('include_archived') === 'true' ? WITH_ARCHIVED : ACTIVE
        );
      }),
      http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.get(`${BASE}/api/v1/entities/categories`, () => HttpResponse.json({ items: [] })),
      http.post(`${BASE}/api/v1/products/:id/restore`, ({ params }) => {
        restoreCalledFor = Number(params.id);
        return HttpResponse.json({ id: Number(params.id), is_active: true });
      })
    );

    renderPage();
    // Archived product hidden by default.
    await screen.findByText('Espresso');
    expect(screen.queryByText('Retired')).not.toBeInTheDocument();

    // Opt in to see archived products.
    await userEvent.click(screen.getByLabelText(/show archived/i));
    const archivedRow = (await screen.findByText('Retired')).closest('tr')!;

    // Restoring posts to the restore endpoint.
    await userEvent.click(within(archivedRow).getByRole('button', { name: /restore/i }));
    expect(restoreCalledFor).toBe(2);
  });
});
