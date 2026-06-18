import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// ISSUE-024 (U1.1 contract drift) — the package "Retail Price/Client" line must
// read the real `suggested_retail_price` returned by GET /api/v1/packages/list.
// Previously it read `retail_price_per_client`, a field the API never returns
// under that name, so the figure always rendered as 0.

const BASE = 'http://127.0.0.1:8000';

const EMPTY_ECONOMICS = {
  total_agents: 0,
  active_agents: 0,
  total_clients: 0,
  active_clients: 0,
  churned_clients: 0,
  mrr: 0,
  arr: 0,
  churn_rate: 0,
  collected: 0,
  platform_revenue: 0,
  by_agent: [],
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

describe('MasterDashboard package retail price (ISSUE-024)', () => {
  it('renders the real suggested_retail_price for a package', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.get(`${BASE}/api/v1/packages/list`, () =>
        HttpResponse.json({
          items: [
            {
              id: 1,
              name: 'Starter',
              client_slots: 5,
              wholesale_price: 50,
              suggested_retail_price: 99,
              is_active: true,
            },
          ],
          total: 1,
        })
      ),
      http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
        HttpResponse.json(EMPTY_ECONOMICS)
      ),
      http.get(`${BASE}/api/v1/entities/audit_logs`, () =>
        HttpResponse.json({ items: [] })
      )
    );
    renderPage();

    const pkgName = await screen.findByText('Starter');
    const card = pkgName.closest('div[class*="rounded-2xl"]')!;
    // The per-client retail price (99.00 ⃁), not the always-0 placeholder.
    expect(within(card as HTMLElement).getByText(/99\.00 ⃁/)).toBeInTheDocument();
  });
});
