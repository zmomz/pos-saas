import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import SubscriptionManagement from './SubscriptionManagement';

// #235 — when the owning agent hasn't connected Moyasar the merchant's
// publishable key is null; every charge would 402. The billing page must
// surface the fail-closed banner (AC1) instead of silently letting a charge fail.

const BASE = 'http://127.0.0.1:8000/api/v1';
const SUB = `${BASE}/tenant/client/subscription`;

const baseSub = {
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
  payments: [],
};

const preview = {
  subscription_status: 'active', billing_cycle: 'monthly', renewal_date: '2026-08-01',
  currency: 'SAR', gross_fee: 200, coupon_active: false, discount_amount: 0,
  net_amount: 200, will_charge: true, in_trial: false, proration: null,
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

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SubscriptionManagement provider fail-closed banner (#235)', () => {
  it('shows the fail-closed banner when the provider has not connected Moyasar', async () => {
    server.use(
      http.get(SUB, () => HttpResponse.json({ ...baseSub, moyasar_publishable_key: null })),
      http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(preview))
    );
    renderPage();
    await waitFor(() => expect(screen.getByTestId('agent-moyasar-banner')).toBeInTheDocument());
  });

  it('does not show the banner once the provider is connected', async () => {
    server.use(
      http.get(SUB, () => HttpResponse.json({ ...baseSub, moyasar_publishable_key: 'pk_test_live' })),
      http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(preview))
    );
    renderPage();
    await waitFor(() => expect(screen.getByText('Upcoming renewal')).toBeInTheDocument());
    expect(screen.queryByTestId('agent-moyasar-banner')).not.toBeInTheDocument();
  });
});
