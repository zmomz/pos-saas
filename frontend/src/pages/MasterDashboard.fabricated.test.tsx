import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// FE-05 — the dashboard must not fabricate data. The backend exposes a single
// live MRR scalar (no historical series), so the hero must NOT synthesize a
// trend line or a hardcoded growth delta; it shows an explicit "no history yet"
// state instead. Real scalars (MRR, ARR, churn) still render.

const BASE = 'http://127.0.0.1:8000';

const ECONOMICS = {
  total_agents: 1,
  active_agents: 1,
  total_clients: 4,
  active_clients: 3,
  churned_clients: 1,
  mrr: 1200,
  arr: 14400,
  churn_rate: 0.05,
  collected: 5000,
  platform_revenue: 800,
  by_agent: [
    {
      agent_id: 1,
      company_name: 'Acme Distribution',
      is_active: true,
      total_clients: 4,
      active_clients: 3,
      mrr: 1200,
      collected: 5000,
      quota_paid: 0,
      payments: 0,
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MasterDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MasterDashboard fabricated data (FE-05)', () => {
  function mountWithEconomics() {
    server.use(
      http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.get(`${BASE}/api/v1/packages/list`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
        HttpResponse.json(ECONOMICS)
      ),
      http.get(`${BASE}/api/v1/entities/audit_logs`, () =>
        HttpResponse.json({ items: [] })
      )
    );
    renderPage();
  }

  it('does not render a fabricated growth delta', async () => {
    mountWithEconomics();
    // Wait for the live MRR scalar to render (real data).
    expect(await screen.findByText('Platform MRR')).toBeInTheDocument();
    // The old hardcoded "+11.4%" hero delta must be gone.
    expect(screen.queryByText(/\+11\.4%/)).not.toBeInTheDocument();
  });

  it('shows an explicit no-history state instead of a synthetic trend', async () => {
    mountWithEconomics();
    expect(await screen.findByText(/trend history not available/i)).toBeInTheDocument();
  });
});
