import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// H4 (#204) — KPI-error isolation. The hero MRR/ARR scalars come from the
// economics endpoint; when it fails, the hero must NOT render a fabricated `0`.
// It shows an honest "—" + retry while the agents list (a separate call that
// succeeded) still renders.

const BASE = 'http://127.0.0.1:8000';

function baseHandlers(economicsStatus: number) {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
      HttpResponse.json({ items: [{ id: 1, company_name: 'Acme', is_active: true, package_type: 5, used_slots: 5 }], total: 1 })
    ),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
      economicsStatus === 200
        ? HttpResponse.json({
            total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
            churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05,
            collected: 5000, platform_revenue: 800, by_agent: [],
          })
        : HttpResponse.json({ detail: 'boom' }, { status: economicsStatus })
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

describe('MasterDashboard economics-error isolation (H4)', () => {
  it('renders an honest unavailable hero MRR (not 0) when economics fails', async () => {
    server.use(...baseHandlers(500));
    renderPage();

    // The hero MRR value renders as the honest unavailable marker, not "0".
    const heroValue = await screen.findByTestId('mrr-hero-value');
    expect(heroValue).toHaveTextContent('—');
    expect(heroValue).not.toHaveTextContent('0');

    // The agents list (a separate, successful call) still renders.
    expect(await screen.findByText(/Acme/)).toBeInTheDocument();
  });

  it('retries economics from the hero and shows the real MRR on recovery', async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
        HttpResponse.json({ items: [{ id: 1, company_name: 'Acme', is_active: true, package_type: 5, used_slots: 5 }], total: 1 })
      ),
      http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
      http.get(`${BASE}/api/v1/tenant/master/economics`, () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json({
          total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
          churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05,
          collected: 5000, platform_revenue: 800, by_agent: [],
        });
      })
    );
    renderPage();

    const retry = await screen.findByTestId('mrr-hero-retry');
    await userEvent.click(retry);

    await waitFor(() => expect(screen.getByTestId('mrr-hero-value')).not.toHaveTextContent('—'));
  });
});
