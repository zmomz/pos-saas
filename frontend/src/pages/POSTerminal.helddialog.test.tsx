import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-226 (M11 FE-Platform · a11y) — the held-tickets overlay was a bespoke raw
// `<div className="fixed inset-0 ...">` with no dialog semantics: no `role="dialog"`,
// no focus trap, and Escape did not close it. This pins the migration onto the shared
// accessible `Dialog` (Radix): a labelled modal that keyboard/SR users can dismiss.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function sideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(PRODUCTS_URL, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () =>
      HttpResponse.json({ items: [{ id: 5, label: 'Table 3', item_count: 2, total_amount: 30 }], total: 1 })
    ),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});
afterAll(() => server.close());

describe('POSTerminal held-tickets modal is an accessible Dialog (ISSUE-226)', () => {
  it('opens a labelled role="dialog" listing parked tickets', async () => {
    server.use(...sideHandlers());
    renderPage();

    const openBtn = await screen.findByRole('button', { name: /held/i });
    await userEvent.click(openBtn);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    // The parked ticket is listed inside the modal.
    expect(within(dialog).getByText('Table 3')).toBeInTheDocument();
  });

  it('closes on Escape (keyboard dismissal)', async () => {
    server.use(...sideHandlers());
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /held/i }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
