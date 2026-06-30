import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// Issue #236 (A4): suspending an agent cascades (SEC-02) to every merchant under
// him and their staff. The master must see "N merchants, M staff will be blocked"
// before confirming. Preview via /tenant/master/agents/{id}/suspend-impact.

const BASE = 'http://127.0.0.1:8000';

function economics() {
  return {
    total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
    churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05, ltv: 8000, cac: null,
    collected: 5000, platform_revenue: 800,
    by_agent: [{
      agent_id: 7, company_name: 'Acme', is_active: true,
      total_clients: 3, active_clients: 3, mrr: 1200,
      collected: 5000, quota_paid: 800, payments: 2,
    }],
  };
}

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () => HttpResponse.json(economics())),
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

describe('MasterDashboard suspend cascade preview (#236 A4)', () => {
  it('previews the merchant + staff blast radius before confirming a suspend', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/api/v1/tenant/master/agents/7/suspend-impact`, () =>
        HttpResponse.json({ agent_id: 7, company_name: 'Acme', merchant_count: 3, staff_count: 5 })
      ),
    );
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByTestId('suspend-agent-7'));

    const merchants = await screen.findByTestId('suspend-impact-merchants');
    expect(merchants).toHaveTextContent('3');
    const staff = await screen.findByTestId('suspend-impact-staff');
    expect(staff).toHaveTextContent('5');
  });

  it('calls the toggle endpoint only after the master confirms', async () => {
    let toggled = false;
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/api/v1/tenant/master/agents/7/suspend-impact`, () =>
        HttpResponse.json({ agent_id: 7, company_name: 'Acme', merchant_count: 3, staff_count: 5 })
      ),
      http.post(`${BASE}/api/v1/tenant/master/agents/7/toggle`, () => {
        toggled = true;
        return HttpResponse.json({ success: true, is_active: false });
      }),
    );
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByTestId('suspend-agent-7'));
    await screen.findByTestId('suspend-impact-merchants');
    expect(toggled).toBe(false);

    await user.click(screen.getByTestId('suspend-confirm'));
    await waitFor(() => expect(toggled).toBe(true));
  });
});
