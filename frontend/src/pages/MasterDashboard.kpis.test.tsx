import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// ISSUE-245 — the master console must surface the buyer-expected KPI set: ARR
// (already shipped) plus LTV (a real aggregate) and CAC. CAC has no acquisition-
// spend source yet, so it renders an honest "—" (FE-05) rather than a fabricated
// number; LTV renders its real money value. On an economics-call failure both
// degrade to "—" alongside the other economics cards (H4 / #204 isolation).

const BASE = 'http://127.0.0.1:8000';

function handlers(opts: { ltv: number | null; cac: number | null; status?: number }) {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
      (opts.status ?? 200) === 200
        ? HttpResponse.json({
            total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
            churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05,
            ltv: opts.ltv, cac: opts.cac,
            collected: 5000, platform_revenue: 800, by_agent: [],
          })
        : HttpResponse.json({ detail: 'boom' }, { status: opts.status })
    ),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MasterDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MasterDashboard LTV/CAC KPIs (ISSUE-245)', () => {
  it('shows the real LTV value and an honest unavailable CAC', async () => {
    server.use(...handlers({ ltv: 8000, cac: null }));
    renderPage();

    const ltv = await screen.findByTestId('kpi-ltv-value');
    expect(ltv).toHaveTextContent('8,000');

    const cac = await screen.findByTestId('kpi-cac-value');
    expect(cac).toHaveTextContent('—');
  });

  it('degrades both cards to "—" when economics fails', async () => {
    server.use(...handlers({ ltv: 8000, cac: null, status: 500 }));
    renderPage();

    const ltv = await screen.findByTestId('kpi-ltv-value');
    expect(ltv).toHaveTextContent('—');
    const cac = await screen.findByTestId('kpi-cac-value');
    expect(cac).toHaveTextContent('—');
  });
});
