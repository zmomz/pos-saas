import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset, extended to the
// agent client-list column-header row. Its headers (Client / Fee / Status /
// ZATCA / Actions) render translated labels under the classic Latin
// `uppercase tracking-wider` overline treatment carried on the header <tr>.
// Arabic joins its letters cursively, so that tracking shatters the joins under
// an Arabic/RTL locale; the base `[dir='rtl']` reset in index.css lives in
// @layer base and loses to Tailwind's utility layer. This mirrors the
// `rtl:tracking-normal` idiom already applied to the MasterDashboard
// agent-leaderboard header, the sidebar nav-section, the ⌘K group headings,
// and the audit-log column headers (#226).

const BASE = 'http://127.0.0.1:8000';

const QUOTA = {
  quota_price: 80, quota_cycle: 'monthly', quota_status: 'active',
  next_quota_billing_date: '2026-07-01', has_card: false, has_moyasar_account: false,
  payments: [],
};

function stubDashboard() {
  server.use(
    http.get(`${BASE}/api/v1/tenant/agent/clients`, () =>
      HttpResponse.json({
        items: [
          {
            id: 3, business_name: 'Corner Shop', email: 'shop@example.com',
            is_active: true, subscription_fee: 100,
          },
        ],
        total: 1, remaining_slots: 5,
      })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () =>
      HttpResponse.json({ collected: 15, payments: 1, by_client: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () => HttpResponse.json(QUOTA)),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () =>
      HttpResponse.json({ statements: [] })
    )
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AgentDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentDashboard client-list header RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on the uppercase client column-header row under RTL', async () => {
    stubDashboard();
    renderPage();

    // The client-list table renders once the clients endpoint resolves.
    const [clientCell] = await screen.findAllByText('Corner Shop', {}, { timeout: 4000 });
    const headerRow = clientCell.closest('table')!.querySelector('thead tr');
    expect(headerRow).not.toBeNull();
    expect(headerRow!.className).toContain('uppercase');
    expect(headerRow!.className).toContain('tracking-wider');
    // Non-color, RTL-only reset so Arabic joins aren't shattered.
    expect(headerRow!.className).toContain('rtl:tracking-normal');
  });
});
