import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import SupplierManagement from './SupplierManagement';

// #273 (Productivity follow-up — bulk ops on remaining list screens). The
// Suppliers book grows the same multi-row selection + undoable bulk delete the
// Products and Customers books already have, via the shared useBulkSelection
// hook. Like the single-row delete, the batch reuses the deferred-commit undo
// primitive: rows drop optimistically and the deletes only reach the server
// once the undo window elapses, so a mis-click is reversible without a restore.

vi.mock('@/lib/undo', () => ({ undoableAction: vi.fn() }));
const mockUndoable = undoableAction as unknown as ReturnType<typeof vi.fn>;

const BASE = 'http://127.0.0.1:8000';
const LIST = {
  items: [
    { id: 's1', name: 'Acme Foods', contact_person: 'Sara', email: 'sara@acme.test', phone: '+966500000001', payment_terms: 'Net 30', vat_number: '300000000000003', status: 'active' },
    { id: 's2', name: 'Beta Beverages', contact_person: 'Omar', email: 'omar@beta.test', phone: '+966500000002', payment_terms: 'Net 60', vat_number: '300000000000004', status: 'active' },
  ],
  total: 2,
};
const EMPTY = { items: [], total: 0 };

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

function baseHandlers(onDelete: (id: string) => void) {
  return [
    http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(LIST)),
    http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(EMPTY)),
    http.delete(`${BASE}/api/v1/entities/suppliers/:id`, ({ params }) => {
      onDelete(String(params.id));
      return HttpResponse.json({});
    }),
  ];
}

async function selectBoth() {
  await userEvent.click(await screen.findByRole('checkbox', { name: /select acme foods/i }));
  await userEvent.click(await screen.findByRole('checkbox', { name: /select beta beverages/i }));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => mockUndoable.mockReset());

describe('SupplierManagement bulk delete (#273)', () => {
  it('defers a bulk delete behind an undo toast and drops rows optimistically', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();

    // A bulk-action bar surfaces the selection count and a delete affordance.
    const bulkDelete = await screen.findByRole('button', { name: /delete selected/i });
    await userEvent.click(bulkDelete);

    // Both rows gone immediately, but nothing deleted on the server yet.
    await waitFor(() => expect(screen.queryByText('Acme Foods')).not.toBeInTheDocument());
    expect(screen.queryByText('Beta Beverages')).not.toBeInTheDocument();
    expect(deleted).toHaveLength(0);
    expect(mockUndoable).toHaveBeenCalledTimes(1);
    const opts = mockUndoable.mock.calls[0][0];
    expect(opts.undoLabel).toBe('Undo');

    // Committing the deferred action deletes every selected row exactly once.
    await opts.onCommit();
    await waitFor(() => expect(deleted.sort()).toEqual(['s1', 's2']));
  });

  it('undo restores the rows without deleting on the server', async () => {
    const deleted: string[] = [];
    server.use(...baseHandlers((id) => deleted.push(id)));
    renderPage();

    await selectBoth();
    await userEvent.click(await screen.findByRole('button', { name: /delete selected/i }));
    await waitFor(() => expect(screen.queryByText('Acme Foods')).not.toBeInTheDocument());

    const opts = mockUndoable.mock.calls[0][0];
    opts.onUndo();

    // Server never received the deletes; the refetch brings both rows back.
    await screen.findByText('Acme Foods');
    await screen.findByText('Beta Beverages');
    expect(deleted).toHaveLength(0);
  });
});
