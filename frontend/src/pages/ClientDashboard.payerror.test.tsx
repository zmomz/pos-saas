import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// FE-04 — a failed subscription payment used to swallow the error to
// console.error, leaving the merchant unsure whether the charge went through.
// A failure now raises a visible error toast.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';

function baseHandlers() {
  return [
    http.get(`${BASE}/tenant/client/dashboard`, () =>
      HttpResponse.json({ today_sales: 0, today_transactions: 0, total_products: 0, low_stock_count: 0 })
    ),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/tenant/client/profile`, () =>
      HttpResponse.json({ client_id: 1, business_name: 'Test Shop', business_type: 'retail', language_preference: 'en' })
    ),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/subscription`, () =>
      HttpResponse.json({
        client_id: 1,
        business_name: 'Test Shop',
        subscription_fee: 50,
        billing_cycle: 'monthly',
        subscription_status: 'past_due',
        is_active: true,
        payments: [],
      })
    ),
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

describe('ClientDashboard subscription payment failure surfacing (FE-04)', () => {
  it('toasts the server error when a subscription payment is rejected', async () => {
    server.use(
      ...baseHandlers(),
      http.post(`${BASE}/tenant/client/subscription/pay`, () =>
        HttpResponse.json({ detail: 'Card declined' }, { status: 402 })
      )
    );

    renderPage();

    const payBtns = await screen.findAllByRole('button', { name: /pay now/i });
    await userEvent.click(payBtns[0]);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Card declined'));
  });
});
