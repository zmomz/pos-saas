import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import SubscriptionManagement from './SubscriptionManagement';

// #206 — the merchant self-serve subscription page. Loads the subscription + the
// renewal preview on mount, and the lifecycle actions (pause/resume/cancel/refund)
// hit their endpoints and re-render from the returned state.

const BASE = 'http://127.0.0.1:8000/api/v1';
const SUB = `${BASE}/tenant/client/subscription`;

const activeSub = {
  client_id: 1,
  business_name: 'Falafel House',
  subscription_fee: 200,
  billing_cycle: 'monthly',
  subscription_status: 'active',
  next_billing_date: '2026-08-01',
  is_active: true,
  has_card: true,
  card_last4: '4242',
  card_brand: 'VISA',
  moyasar_publishable_key: null,
  payments: [
    { id: 11, amount: 200, billing_cycle: 'monthly', period_start: '2026-07-01', method: 'sandbox', created_at: '2026-07-01' },
  ],
};

const activePreview = {
  subscription_status: 'active',
  billing_cycle: 'monthly',
  renewal_date: '2026-08-01',
  currency: 'SAR',
  gross_fee: 200,
  coupon_active: false,
  discount_amount: 0,
  net_amount: 200,
  will_charge: true,
  in_trial: false,
  proration: null,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ThemeProvider>
          <SubscriptionManagement />
        </ThemeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SubscriptionManagement (#206)', () => {
  it('shows the upcoming renewal, plan, masked card and invoice history', async () => {
    server.use(
      http.get(SUB, () => HttpResponse.json(activeSub)),
      http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(activePreview))
    );

    renderPage();

    await waitFor(() => expect(screen.getByText('Upcoming renewal')).toBeInTheDocument());
    // Masked card on file + billing history row.
    expect(screen.getByText(/4242/)).toBeInTheDocument();
    expect(screen.getByText(/VISA/)).toBeInTheDocument();
    expect(screen.getByText('Billing history')).toBeInTheDocument();
  });

  it('pauses billing through the pause endpoint after confirming', async () => {
    const paused = vi.fn();
    server.use(
      http.get(SUB, () => HttpResponse.json(activeSub)),
      http.get(`${SUB}/renewal-preview`, () =>
        HttpResponse.json({ ...activePreview, will_charge: false, subscription_status: 'paused' })
      ),
      http.post(`${SUB}/pause`, () => {
        paused();
        return HttpResponse.json({ ...activeSub, subscription_status: 'paused', subscription_paused_at: '2026-07-10' });
      })
    );

    renderPage();
    await waitFor(() => expect(screen.getByText('Pause')).toBeInTheDocument());

    await userEvent.click(screen.getByText('Pause'));
    // Confirm in the dialog (the destructive/confirm action carries the same label).
    const confirmBtns = await screen.findAllByText('Pause');
    await userEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => expect(paused).toHaveBeenCalled());
  });

  it('refunds a settled payment through the refund endpoint', async () => {
    const refunded = vi.fn();
    server.use(
      http.get(SUB, () => HttpResponse.json(activeSub)),
      http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(activePreview)),
      http.post(`${SUB}/payments/11/refund`, () => {
        refunded();
        return HttpResponse.json({
          ...activeSub,
          payments: [
            ...activeSub.payments,
            { id: 12, amount: -200, method: 'refund', created_at: '2026-07-05' },
          ],
        });
      })
    );

    renderPage();
    await waitFor(() => expect(screen.getByText('Billing history')).toBeInTheDocument());

    await userEvent.click(screen.getByTitle('Refund'));
    // Confirm the refund.
    const confirm = await screen.findAllByText('Refund');
    await userEvent.click(confirm[confirm.length - 1]);

    await waitFor(() => expect(refunded).toHaveBeenCalled());
  });
});
