import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import DiscountManagement from './DiscountManagement';

// #231 (Productivity — undo). Deleting a discount no longer hits the server
// outright: the row is dropped optimistically and the delete is deferred behind
// an undo toast, so a mis-click is reversible without a compensating restore.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [{ id: '1', code: 'SAVE10', type: 'percentage', value: 10, is_active: true }],
  total: 1,
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

function baseHandlers(onDelete: () => void) {
  return [
    http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)),
    http.delete(`${BASE}/api/v1/entities/discounts/:id`, () => {
      onDelete();
      return HttpResponse.json({});
    }),
  ];
}

async function confirmDelete() {
  const row = (await screen.findByText('SAVE10')).closest('tr')!;
  await userEvent.click(within(row as HTMLElement).getByRole('button', { name: /delete/i }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('DiscountManagement delete undo (#231)', () => {
  it('defers the delete behind an undo toast and drops the row optimistically', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    renderPage();

    await confirmDelete();

    // Row gone immediately, but nothing deleted on the server yet.
    await waitFor(() => expect(screen.queryByText('SAVE10')).not.toBeInTheDocument());
    expect(deletes).toBe(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.message).toBe('Discount deleted');
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action deletes it for real.
    await opts.onCommit();
    await waitFor(() => expect(deletes).toBe(1));
  });

  it('undo restores the row without deleting on the server', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    renderPage();

    await confirmDelete();
    await waitFor(() => expect(screen.queryByText('SAVE10')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the delete; the refetch brings the row back.
    await screen.findByText('SAVE10');
    expect(deletes).toBe(0);
  });
});
