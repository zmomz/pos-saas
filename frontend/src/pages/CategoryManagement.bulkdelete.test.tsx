import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import CategoryManagement from './CategoryManagement';

// #273 (Productivity follow-up — bulk ops on remaining list screens). The
// Categories book grows the same multi-row selection + undoable bulk delete the
// Products, Customers and Suppliers books already have, via the shared
// useBulkSelection hook. Like the single-row delete, the batch reuses the
// deferred-commit undo primitive: rows drop optimistically and the deletes only
// reach the server once the undo window elapses, so a mis-click is reversible
// without a restore round-trip.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [
    { id: 'c1', name: 'Beverages', parent_id: null, icon: '', sort_order: 0 },
    { id: 'c2', name: 'Bakery', parent_id: null, icon: '', sort_order: 1 },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CategoryManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function baseHandlers(onDelete: (id: string) => void) {
  return [
    http.get(`${BASE}/api/v1/entities/categories`, () => HttpResponse.json(LIST)),
    http.delete(`${BASE}/api/v1/entities/categories/:id`, ({ params }) => {
      onDelete(String(params.id));
      return HttpResponse.json({});
    }),
  ];
}

async function selectBoth() {
  await userEvent.click(await screen.findByRole('checkbox', { name: /select beverages/i }));
  await userEvent.click(await screen.findByRole('checkbox', { name: /select bakery/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('CategoryManagement bulk delete (#273)', () => {
  it('defers a bulk delete behind an undo toast and drops rows optimistically', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();

    // A bulk-action bar surfaces the selection count and a delete affordance.
    const bulkDelete = await screen.findByRole('button', { name: /delete selected/i });
    await userEvent.click(bulkDelete);

    // Both rows gone immediately, but nothing deleted on the server yet.
    await waitFor(() => expect(screen.queryByText('Beverages')).not.toBeInTheDocument());
    expect(screen.queryByText('Bakery')).not.toBeInTheDocument();
    expect(deleted).toHaveLength(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action deletes every selected row exactly once.
    await opts.onCommit();
    await waitFor(() => expect(deleted.sort()).toEqual(['c1', 'c2']));
  });

  it('undo restores the rows without deleting on the server', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();
    await userEvent.click(await screen.findByRole('button', { name: /delete selected/i }));
    await waitFor(() => expect(screen.queryByText('Beverages')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the deletes; the refetch brings both rows back.
    await screen.findByText('Beverages');
    await screen.findByText('Bakery');
    expect(deleted).toHaveLength(0);
  });
});
