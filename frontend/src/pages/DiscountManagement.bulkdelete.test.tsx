import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import DiscountManagement from './DiscountManagement';

// #231 (Productivity — bulk ops). Operators can select several discount rows and
// delete them in one action. Like the single-row delete, the batch reuses the
// deferred-commit undo primitive: rows drop optimistically and the deletes only
// reach the server once the undo window elapses, so a mis-click is reversible
// without a restore round-trip. Third page onto the shared useBulkSelection hook.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [
    { id: 'd1', code: 'SAVE10', type: 'percentage', value: 10, is_active: true },
    { id: 'd2', code: 'SAVE20', type: 'percentage', value: 20, is_active: true },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DiscountManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function baseHandlers(onDelete: (id: string) => void) {
  return [
    http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)),
    http.delete(`${BASE}/api/v1/entities/discounts/:id`, ({ params }) => {
      onDelete(String(params.id));
      return HttpResponse.json({});
    }),
  ];
}

async function selectBoth() {
  await userEvent.click(await screen.findByRole('checkbox', { name: /select save10/i }));
  await userEvent.click(await screen.findByRole('checkbox', { name: /select save20/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('DiscountManagement bulk delete (#231)', () => {
  it('defers a bulk delete behind an undo toast and drops rows optimistically', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();

    // A bulk-action bar surfaces the selection count and a delete affordance.
    const bulkDelete = await screen.findByRole('button', { name: /delete selected/i });
    await userEvent.click(bulkDelete);

    // Both rows gone immediately, but nothing deleted on the server yet.
    await waitFor(() => expect(screen.queryByText('SAVE10')).not.toBeInTheDocument());
    expect(screen.queryByText('SAVE20')).not.toBeInTheDocument();
    expect(deleted).toHaveLength(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action deletes every selected row exactly once.
    await opts.onCommit();
    await waitFor(() => expect(deleted.sort()).toEqual(['d1', 'd2']));
  });

  it('undo restores the rows without deleting on the server', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();
    await userEvent.click(await screen.findByRole('button', { name: /delete selected/i }));
    await waitFor(() => expect(screen.queryByText('SAVE10')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the deletes; the refetch brings both rows back.
    await screen.findByText('SAVE10');
    await screen.findByText('SAVE20');
    expect(deleted).toHaveLength(0);
  });
});
