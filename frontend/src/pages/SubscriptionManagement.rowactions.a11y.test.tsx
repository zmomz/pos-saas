import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import SubscriptionManagement from './SubscriptionManagement';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the billing-history row
// actions. Each settled payment row carries two icon-only controls: Download
// invoice (Download glyph) and Refund (Undo2 glyph). Their visible text label is
// `hidden sm:inline`, so below the `sm` breakpoint the button collapses to an
// icon with only a `title` for a name. `title` is an unreliable accessible name
// for icon-only controls (touch and keyboard-only users get no hover tooltip and
// several screen readers don't announce it) — the same gap already hardened on
// the AgentDashboard merchant-row cluster. WCAG 4.1.2 Name, Role, Value wants an
// explicit `aria-label` that survives the responsive collapse. This suite pins
// that contract on the invoice-row action cluster.

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
  // A real positive gateway charge: refundable AND downloadable, so both
  // icon-only row controls render.
  payments: [
    { id: 11, amount: 200, billing_cycle: 'monthly', period_start: '2026-07-01', method: 'card', created_at: '2026-07-01' },
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

function useHandlers() {
  server.use(
    http.get(SUB, () => HttpResponse.json(activeSub)),
    http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(activePreview))
  );
}

describe('SubscriptionManagement invoice-row action a11y (#226)', () => {
  it('gives the icon-only Download-invoice control an explicit aria-label', async () => {
    useHandlers();
    renderPage();
    await waitFor(() => expect(screen.getByText('Billing history')).toBeInTheDocument());
    const btn = screen.getByRole('button', { name: 'Download invoice' });
    expect(btn).toHaveAttribute('aria-label', 'Download invoice');
  });

  it('gives the icon-only Refund control an explicit aria-label', async () => {
    useHandlers();
    renderPage();
    await waitFor(() => expect(screen.getByText('Billing history')).toBeInTheDocument());
    const btn = screen.getByRole('button', { name: 'Refund' });
    expect(btn).toHaveAttribute('aria-label', 'Refund');
  });
});
