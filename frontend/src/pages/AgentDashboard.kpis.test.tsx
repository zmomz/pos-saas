import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// ISSUE-245 — the agent dashboard surfaces operating KPIs: active merchants,
// merchant growth (this window vs prior) and trial expiry, sourced from the
// dedicated /agent/dashboard-kpis aggregate. A failure of that one call degrades
// only those cards to an honest "—" (H4 / #204), never the rest of the dashboard.

const BASE = 'http://127.0.0.1:8000';

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/agent/clients`, () =>
      HttpResponse.json({ items: [], total: 0, remaining_slots: 4 })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () =>
      HttpResponse.json({ collected: 0, payments: 0, by_client: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () =>
      HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: true, payments: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] })),
  ];
}

function kpisHandler(status: number) {
  return http.get(`${BASE}/api/v1/tenant/agent/dashboard-kpis`, () =>
    status === 200
      ? HttpResponse.json({
          active_merchants: 7,
          total_merchants: 9,
          merchant_growth: { new_current: 3, new_previous: 1, delta: 2 },
          trial_expiry: { expiring_soon: 2, next_trial_end: '2026-07-05' },
          revenue_trend: [{ month: '2026-06', amount: 100 }],
        })
      : HttpResponse.json({ detail: 'boom' }, { status })
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

describe('AgentDashboard KPIs (ISSUE-245)', () => {
  it('renders active-merchants, growth and trial-expiry from the KPI aggregate', async () => {
    server.use(...baseHandlers(), kpisHandler(200));
    renderPage();

    expect(await screen.findByTestId('kpi-active-merchants')).toHaveTextContent('7');
    expect(screen.getByTestId('kpi-merchant-growth')).toHaveTextContent('3');
    expect(screen.getByTestId('kpi-trial-expiry')).toHaveTextContent('2');
  });

  it('degrades only the KPI cards to "—" when the aggregate fails', async () => {
    server.use(...baseHandlers(), kpisHandler(500));
    renderPage();

    expect(await screen.findByTestId('kpi-active-merchants')).toHaveTextContent('—');
    expect(screen.getByTestId('kpi-trial-expiry')).toHaveTextContent('—');
    // The rest of the dashboard (the stats bento) still renders.
    expect(document.querySelector('[data-tour="stats-section"]')).toBeInTheDocument();
  });
});
