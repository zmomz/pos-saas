import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within, act, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import ProductManagement from './ProductManagement';

// #231 (Productivity — undo). Deleting a product no longer archives it on the
// server outright: the row is dropped optimistically and the archive is deferred
// behind an undo toast, so a mis-click is reversible without a restore round-trip.
//
// Determinism note: ProductManagement runs an immediate mount fetch AND a 300ms
// *debounced* re-fetch (the search/filter effect fires once on mount). With real
// timers that debounced re-fetch lands at an unpredictable point relative to the
// delete interaction; when it lands AFTER the optimistic removal it re-reads the
// server (which still holds the row — the archive is deferred) and RESURRECTS
// the row, timing out the "row gone" / mockUndoable assertions ~1/3 of runs.
// We use fake timers to flush the mount fetches and the debounce BEFORE
// interacting, so no pending timer can re-fetch mid-assertion.

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

// Render, then drain the mount fetches AND the 300ms debounced re-fetch so the
// page is fully idle (no pending timer) before we interact.
async function renderAndSettle() {
  renderPage();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  // Row is present and stable now.
  expect(screen.getByText('Espresso')).toBeInTheDocument();
}

async function confirmDelete() {
  const row = screen.getByText('Espresso').closest('tr')!;
  await act(async () => {
    fireEvent.click(within(row).getByRole('button', { name: /delete/i }));
  });
  const dialog = screen.getByRole('dialog');
  await act(async () => {
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
  });
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});
afterAll(() => server.close());
beforeEach(() => {
  mockUndoable.mockReset();
  vi.useFakeTimers();
});

describe('ProductManagement delete undo (#231)', () => {
  it('defers the archive behind an undo toast and drops the row optimistically', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    await renderAndSettle();

    await confirmDelete();

    // Row gone immediately (optimistic), but nothing archived on the server yet.
    expect(screen.queryByText('Espresso')).not.toBeInTheDocument();
    expect(deletes).toBe(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action archives it for real.
    await act(async () => {
      await opts.onCommit();
    });
    expect(deletes).toBe(1);
  });

  it('undo restores the row without archiving on the server', async () => {
    let deletes = 0;
    server.use(...baseHandlers(() => (deletes += 1)));
    await renderAndSettle();

    await confirmDelete();
    expect(screen.queryByText('Espresso')).not.toBeInTheDocument();

    const opts = mockUndoable.mock.calls[0][0];
    // Undo cancels the commit and refetches — the server never saw the delete,
    // so the row comes back.
    await act(async () => {
      opts.onUndo();
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText('Espresso')).toBeInTheDocument();
    expect(deletes).toBe(0);
  });
});
