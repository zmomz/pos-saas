import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// FE-04 — a failed checkout used to swallow the error to console.error, so the
// cashier got no signal the sale did NOT go through (no receipt, cart still
// full). A failure now raises a visible error toast.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});
afterAll(() => server.close());

describe('POSTerminal checkout failure surfacing (FE-04)', () => {
  it('toasts the server error when the (online) sale is rejected', async () => {
    server.use(
      http.get(PRODUCTS_URL, () =>
        HttpResponse.json([{ id: 1, name: 'Juice', price: 12, vat_rate: 0.15 }])
      ),
      http.post(`${BASE}/pos/transaction`, () =>
        HttpResponse.json({ detail: 'Insufficient stock' }, { status: 400 })
      ),
      ...mountSideHandlers()
    );

    renderPage();

    await userEvent.click(await screen.findByText('Juice'));
    await userEvent.click(screen.getByRole('button', { name: /^pay\b/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Insufficient stock'));
  });
});
