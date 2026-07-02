import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. Each commission
// statement heads its billing period as `{period_start} → {period_end}`. The
// literal RIGHTWARDS ARROW is a bidi-neutral glyph: the browser does NOT mirror
// it under `[dir="rtl"]`, so an Arabic/Urdu reader (who scans right-to-left) sees
// it point *away* from the period end. The dashboards' idiom for a mirrored
// horizontal arrow is Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180`
// too), and the glyph is decorative — both dates are already visible — so it must
// also be `aria-hidden`.

const BASE = 'http://127.0.0.1:8000';

const STATEMENTS = {
  statements: [
    {
      period_start: '2026-06-01',
      period_end: '2026-07-01',
      billing_cycle: 'monthly',
      collected: 15,
      payments: 1,
      by_client: [
        { client_id: 3, business_name: 'Corner Shop', collected: 15, payments: 1 },
      ],
    },
  ],
};

const QUOTA = {
  quota_price: 80, quota_cycle: 'monthly', quota_status: 'active',
  next_quota_billing_date: '2026-07-01', has_card: false, has_moyasar_account: false,
  payments: [],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AgentDashboard />
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

function stubDashboard() {
  server.use(
    http.get(`${BASE}/api/v1/tenant/agent/clients`, () => HttpResponse.json({ items: [], total: 0, remaining_slots: 5 })),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 15, payments: 1, by_client: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () => HttpResponse.json(QUOTA)),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json(STATEMENTS))
  );
}

describe('AgentDashboard commission-statement period arrow RTL mirroring (ISSUE-226)', () => {
  it('mirrors the period start→end arrow and hides it from SR', async () => {
    stubDashboard();
    renderPage();

    // The statement period heading surfaces the window.
    await screen.findByText(/2026-06-01/);
    const arrow = screen.getByText('→');
    expect(isMirrored(arrow)).toBe(true);
    // Decorative: both dates are already visible, so the glyph must not be announced.
    expect(arrow.getAttribute('aria-hidden')).toBe('true');
  });
});
