import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import GuidedStocktake from './GuidedStocktake';

// M4 / #207 — the guided stocktake page drives start → freeze → count → approve
// over /api/v1/production/stock-counts. These tests pin the list/empty states and
// the freeze → count interaction against the real api client.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <GuidedStocktake />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('GuidedStocktake', () => {
  it('shows the empty state when there are no stocktakes', async () => {
    server.use(
      http.get(`${BASE}/api/v1/production/stock-counts`, () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
      http.get(`${BASE}/api/v1/entities/branches`, () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
    );
    renderPage();
    expect(await screen.findByText('No stocktakes yet')).toBeInTheDocument();
  });

  it('lists a draft session and opens it to the freeze step', async () => {
    server.use(
      http.get(`${BASE}/api/v1/production/stock-counts`, () =>
        HttpResponse.json({
          items: [
            { id: 7, branch_id: 1, name: 'Month-end', status: 'draft', created_at: '2026-06-29' },
          ],
          total: 1,
        }),
      ),
      http.get(`${BASE}/api/v1/entities/branches`, () =>
        HttpResponse.json({ items: [{ id: 1, name: 'Main' }], total: 1 }),
      ),
      http.get(`${BASE}/api/v1/production/stock-counts/7`, () =>
        HttpResponse.json({ id: 7, branch_id: 1, name: 'Month-end', status: 'draft', lines: [] }),
      ),
    );
    renderPage();

    const row = (await screen.findByText('Month-end')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Resume' }));

    // The draft opens on the freeze step with the explanatory CTA.
    expect(await screen.findByText('Freeze the on-hand baseline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Freeze stock/ })).toBeInTheDocument();
  });

  it('records a barcode count against a frozen session', async () => {
    let counted: { barcode?: string; counted_quantity?: number } | null = null;
    server.use(
      http.get(`${BASE}/api/v1/production/stock-counts`, () =>
        HttpResponse.json({
          items: [{ id: 9, branch_id: 1, name: 'Count', status: 'frozen', created_at: '2026-06-29' }],
          total: 1,
        }),
      ),
      http.get(`${BASE}/api/v1/entities/branches`, () =>
        HttpResponse.json({ items: [{ id: 1, name: 'Main' }], total: 1 }),
      ),
      http.get(`${BASE}/api/v1/production/stock-counts/9`, () =>
        HttpResponse.json({
          id: 9,
          branch_id: 1,
          name: 'Count',
          status: 'frozen',
          lines: [
            {
              id: 1,
              product_id: 100,
              product_name: 'Apples',
              system_quantity: 50,
              counted_quantity: null,
              variance: null,
              counted: false,
            },
          ],
        }),
      ),
      http.post(`${BASE}/api/v1/production/stock-counts/9/count`, async ({ request }) => {
        counted = (await request.json()) as { barcode?: string; counted_quantity?: number };
        return HttpResponse.json({
          id: 1,
          session_id: 9,
          product_id: 100,
          product_name: 'Apples',
          system_quantity: 50,
          counted_quantity: 47,
          variance: -3,
        });
      }),
    );
    renderPage();

    const row = (await screen.findByText('Count')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Resume' }));

    // The frozen session shows the scanner.
    const scan = await screen.findByPlaceholderText('Scan or enter a barcode');
    await userEvent.type(scan, '5012345678900');
    const qty = screen.getByLabelText('Counted quantity');
    await userEvent.clear(qty);
    await userEvent.type(qty, '47');
    await userEvent.click(screen.getByRole('button', { name: 'Record count' }));

    // The variance lands on the line (badge) and the net-variance tile.
    const variances = await screen.findAllByText('-3');
    expect(variances.length).toBeGreaterThanOrEqual(1);
    expect(counted).toEqual({ barcode: '5012345678900', counted_quantity: 47 });
  });
});
