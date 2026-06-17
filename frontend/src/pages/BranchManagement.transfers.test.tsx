import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BranchManagement from './BranchManagement';

// ISSUE-060 — a merchant reviews inter-branch stock-transfer history from the
// Branch Management screen: a "Transfer History" view lists past transfers
// (from/to branch, product, qty, status, date) and can be filtered by branch.

const BASE = 'http://127.0.0.1:8000';

const TWO_BRANCHES = {
  items: [
    { id: 1, name: 'Downtown', is_active: true, is_main: true },
    { id: 2, name: 'Airport', is_active: true, is_main: false },
  ],
  total: 2,
};

const TRANSFERS = {
  items: [
    { id: 2, from_branch_id: 1, to_branch_id: 2, product_id: 9, product_name: 'Latte', quantity: 7, status: 'received', created_at: '2026-06-13T10:00:00' },
    { id: 1, from_branch_id: 2, to_branch_id: 1, product_id: 8, product_name: 'Mocha', quantity: 3, status: 'received', created_at: '2026-06-12T09:00:00' },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <BranchManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BranchManagement transfer history (ISSUE-060)', () => {
  it('lists past transfers when the history view is opened', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(TWO_BRANCHES)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/api/v1/production/branches/transfers`, () => HttpResponse.json(TRANSFERS))
    );
    renderPage();

    const btn = await screen.findByRole('button', { name: /transfer history/i });
    await userEvent.click(btn);

    // The dialog lists each transfer with product, qty and resolved branch names.
    expect(await screen.findByText('Latte')).toBeInTheDocument();
    expect(screen.getByText('Mocha')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getAllByText('Downtown').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('Airport').length).toBeGreaterThan(0);
  });

  it('filters the history by branch', async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(TWO_BRANCHES)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/api/v1/production/branches/transfers`, ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('branch_id'));
        return HttpResponse.json(TRANSFERS);
      })
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /transfer history/i }));
    await screen.findByText('Latte');

    // Choosing a branch in the filter refetches scoped to that branch.
    const dialog = screen.getByRole('dialog');
    const filter = within(dialog).getByRole('combobox');
    await userEvent.click(filter);
    await userEvent.click(await screen.findByRole('option', { name: 'Airport' }));
    await waitFor(() => expect(seen).toContain('2'));
  });
});
