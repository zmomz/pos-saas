import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import ProductManagement from './ProductManagement';

// #231 (Productivity — undo). Deleting a product no longer archives it on the
// server outright: the row is dropped optimistically and the archive is deferred
// behind an undo toast, so a mis-click is reversible without a restore round-trip.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [{ id: 1, name: 'Espresso', price: 10, quantity: 5, vat_rate: 15, is_active: true }],
  total: 1,
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

function baseHandlers(onDelete: () => void) {
  return [
    http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(LIST)),
    http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/entities/categories`, () => HttpResponse.json({ items: [] })),
    http.delete(`${BASE}/api/v1/products/:id`, () => {
      onDelete();
      return HttpResponse.json({});
    }),
  ];
}

async function confirmDelete() {
  const row = (await screen.findByText('Espresso')).closest('tr')!;
  await userEvent.click(within(row).getByRole('button', { name: /delete/i }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('ProductManagement delete undo (#231)', () => {
  it('defers the archive behind an undo toast and drops the row optimistically', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    renderPage();

    await confirmDelete();

    // Row gone immediately, but nothing archived on the server yet.
    await waitFor(() => expect(screen.queryByText('Espresso')).not.toBeInTheDocument());
    expect(deletes).toBe(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action archives it for real.
    await opts.onCommit();
    await waitFor(() => expect(deletes).toBe(1));
  });

  it('undo restores the row without archiving on the server', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    renderPage();

    await confirmDelete();
    await waitFor(() => expect(screen.queryByText('Espresso')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the delete; the refetch brings the row back.
    await screen.findByText('Espresso');
    expect(deletes).toBe(0);
  });
});
