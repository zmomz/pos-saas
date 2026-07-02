import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import SubscriptionManagement from './SubscriptionManagement';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. Each settled
// billing-history row exposes a Refund control drawn with the lucide `Undo2`
// glyph: a curved arrow that loops back toward the *start* of the reading
// direction. A lucide icon is an inline SVG the browser does NOT mirror under
// `[dir="rtl"]`, so an Arabic/Urdu reader (who scans right-to-left) sees the
// "undo" arrow curve the wrong way — it reads as "redo". Per Material Design
// bidirectionality, undo/redo glyphs are mirrored in RTL; the dashboards' idiom
// is Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180` too).

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
  // A real positive gateway charge: refundable, so the Refund control renders.
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

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SubscriptionManagement refund-icon RTL mirroring (ISSUE-226)', () => {
  it('mirrors the Undo2 refund glyph so it curves the right way in RTL', async () => {
    server.use(
      http.get(SUB, () => HttpResponse.json(activeSub)),
      http.get(`${SUB}/renewal-preview`, () => HttpResponse.json(activePreview))
    );

    renderPage();
    await waitFor(() => expect(screen.getByText('Billing history')).toBeInTheDocument());

    const refund = screen.getByRole('button', { name: 'Refund' });
    expect(isMirrored(refund.querySelector('svg'))).toBe(true);
  });
});
