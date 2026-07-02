import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import ProductManagement from './ProductManagement';

// #231 (Productivity — bulk ops). Operators can select several catalog rows and
// archive them in one action. The bulk delete reuses the deferred-commit undo
// primitive: rows drop optimistically and the archive only reaches the server
// once the undo window elapses, so a mis-click is reversible without a restore
// round-trip.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [
    { id: 1, name: 'Espresso', price: 10, quantity: 5, vat_rate: 15, is_active: true },
    { id: 2, name: 'Latte', price: 12, quantity: 8, vat_rate: 15, is_active: true },
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

function baseHandlers(onDelete: (id: string) => void) {
  return [
    http.get(`${BASE}/api/v1/products/list`, () => HttpResponse.json(LIST)),
    http.get(`${BASE}/api/v1/products/reorder-suggestions`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/entities/categories`, () => HttpResponse.json({ items: [] })),
    http.delete(`${BASE}/api/v1/products/:id`, ({ params }) => {
      onDelete(String(params.id));
      return HttpResponse.json({});
    }),
  ];
}

async function selectBoth() {
  await userEvent.click(await screen.findByRole('checkbox', { name: /select espresso/i }));
  await userEvent.click(await screen.findByRole('checkbox', { name: /select latte/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('ProductManagement bulk delete (#231)', () => {
  it('defers a bulk archive behind an undo toast and drops rows optimistically', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();

    // A bulk-action bar surfaces the selection count and a delete affordance.
    const bulkDelete = await screen.findByRole('button', { name: /delete selected/i });
    await userEvent.click(bulkDelete);

    // Both rows gone immediately, but nothing archived on the server yet.
    await waitFor(() => expect(screen.queryByText('Espresso')).not.toBeInTheDocument());
    expect(screen.queryByText('Latte')).not.toBeInTheDocument();
    expect(deleted).toHaveLength(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action archives every selected row exactly once.
    await opts.onCommit();
    await waitFor(() => expect(deleted.sort()).toEqual(['1', '2']));
  });

  it('undo restores the rows without archiving on the server', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();
    await userEvent.click(await screen.findByRole('button', { name: /delete selected/i }));
    await waitFor(() => expect(screen.queryByText('Espresso')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the deletes; the refetch brings both rows back.
    await screen.findByText('Espresso');
    await screen.findByText('Latte');
    expect(deleted).toHaveLength(0);
  });
});
