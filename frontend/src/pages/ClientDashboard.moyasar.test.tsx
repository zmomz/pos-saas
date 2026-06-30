import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// #235 — the merchant home is a billing surface too. When the owning agent
// hasn't connected Moyasar, show the fail-closed banner (AC1) and disable the
// inline "Pay now" so the merchant can't fire a charge that will 402 (AC2).

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';

const sub = (key: string | null) => ({
  client_id: 1,
  business_name: 'Falafel House',
  subscription_fee: 200,
  billing_cycle: 'monthly',
  subscription_status: 'active',
  next_billing_date: '2026-08-01',
  is_active: true,
  moyasar_publishable_key: key,
  payments: [],
});

function handlers(key: string | null) {
  return [
    http.get(`${BASE}/tenant/client/dashboard`, () =>
      HttpResponse.json({ total_sales: 1000, today_sales: 250, total_transactions: 8, today_transactions: 3, products_count: 12 })
    ),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/subscription`, () => HttpResponse.json(sub(key))),
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
afterEach(() => { server.resetHandlers(); vi.clearAllMocks(); });
afterAll(() => server.close());

describe('ClientDashboard provider fail-closed (#235)', () => {
  it('shows the banner and disables Pay now when the provider is not connected', async () => {
    server.use(...handlers(null));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('agent-moyasar-banner')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /pay now/i })).toBeDisabled();
  });

  it('enables Pay now and hides the banner once the provider is connected', async () => {
    server.use(...handlers('pk_test_live'));
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: /pay now/i })).toBeEnabled());
    expect(screen.queryByTestId('agent-moyasar-banner')).not.toBeInTheDocument();
  });
});
