import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// H4 — the first-impression dashboard adapts to the merchant's business_type and
// tells the truth on a failed load (no all-zero fake KPIs).

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';

const STATS = { total_sales: 1000, today_sales: 200, total_transactions: 8, today_transactions: 2, products_count: 12 };

function handlers(businessType: string) {
  return [
    http.get(`${BASE}/tenant/client/dashboard`, () => HttpResponse.json(STATS)),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/tenant/client/profile`, () =>
      HttpResponse.json({ client_id: 1, business_name: 'Test Shop', business_type: businessType, language_preference: 'en' })
    ),
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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});
afterAll(() => server.close());

describe('ClientDashboard business-type adaptation (H4)', () => {
  it('a retail merchant sees retail metrics + language', async () => {
    server.use(...handlers('retail'));
    renderPage();
    expect(await screen.findByText('Avg Ticket')).toBeInTheDocument();
    expect(screen.getByText('Recent Transactions')).toBeInTheDocument();
    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.queryByText('Avg Check')).not.toBeInTheDocument();
  });

  it('a restaurant merchant sees restaurant metrics + language', async () => {
    server.use(...handlers('restaurant'));
    renderPage();
    expect(await screen.findByText('Avg Check')).toBeInTheDocument();
    expect(screen.getByText('Recent Orders')).toBeInTheDocument();
    expect(screen.getByText('Menu Items')).toBeInTheDocument();
    expect(screen.queryByText('Avg Ticket')).not.toBeInTheDocument();
  });
});

describe('ClientDashboard load failure honesty (H4)', () => {
  it('shows an error + retry instead of all-zero KPIs when stats fail', async () => {
    server.use(
      http.get(`${BASE}/tenant/client/dashboard`, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      ...handlers('retail')
    );
    renderPage();

    // Error surface with retry, and NO fabricated KPI tiles.
    expect(await screen.findByText('Could not load your dashboard')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByText('Total Sales')).not.toBeInTheDocument();

    // Retry recovers once the endpoint is healthy again.
    server.resetHandlers();
    server.use(...handlers('retail'));
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => expect(screen.getByText('Total Sales')).toBeInTheDocument());
  });
});
