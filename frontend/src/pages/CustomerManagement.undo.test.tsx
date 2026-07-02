import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import CustomerManagement from './CustomerManagement';

// #231 (Productivity — undo). Deleting a customer no longer hits the server
// outright: the row is dropped optimistically and the delete is deferred behind
// an undo toast, so a mis-click is reversible without a compensating restore.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [
    { id: 'c1', name: 'Layla Hassan', phone: '+966500000001', email: 'layla@example.com', tags: [], pii_erased_at: null },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CustomerManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function baseHandlers(onDelete: () => void) {
  return [
    http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(LIST)),
    http.delete(`${BASE}/api/v1/entities/customers/:id`, () => {
      onDelete();
      return HttpResponse.json({});
    }),
  ];
}

async function confirmDelete() {
  const row = (await screen.findByText('Layla Hassan')).closest('tr')!;
  await userEvent.click(within(row as HTMLElement).getByRole('button', { name: /^delete$/i }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('CustomerManagement delete undo (#231)', () => {
  it('defers the delete behind an undo toast and drops the row optimistically', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    renderPage();

    await confirmDelete();

    // Row gone immediately, but nothing deleted on the server yet.
    await waitFor(() => expect(screen.queryByText('Layla Hassan')).not.toBeInTheDocument());
    expect(deletes).toBe(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.message).toBe('Customer deleted');
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
    await waitFor(() => expect(screen.queryByText('Layla Hassan')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the delete; the refetch brings the row back.
    await screen.findByText('Layla Hassan');
    expect(deletes).toBe(0);
  });
});
