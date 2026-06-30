import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// H4 (#204) — the first-impression dashboard must not render an all-zero fake
// when the core stats load fails. A failed `/tenant/client/dashboard` shows an
// ErrorState + retry, never fabricated KPIs.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';

function secondaryHandlers() {
  return [
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/subscription`, () => HttpResponse.json(null)),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ClientDashboard />
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

describe('ClientDashboard load-failure honesty (H4)', () => {
  it('shows an error+retry instead of all-zero KPIs when the dashboard fetch fails', async () => {
    server.use(
      http.get(`${BASE}/tenant/client/dashboard`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 })
      ),
      ...secondaryHandlers()
    );

    renderPage();

    // The honest error state appears...
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    // ...and the fabricated "Today's Sales" headline KPI is NOT rendered.
    expect(screen.queryByText(/today's sales/i)).not.toBeInTheDocument();
  });

  it('retry refetches and renders the real KPIs once the server recovers', async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/tenant/client/dashboard`, () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json({
          total_sales: 1000,
          today_sales: 250,
          total_transactions: 8,
          today_transactions: 3,
          products_count: 12,
        });
      }),
      ...secondaryHandlers()
    );

    renderPage();

    await screen.findByRole('button', { name: /retry/i });
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByText(/today's sales/i)).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
