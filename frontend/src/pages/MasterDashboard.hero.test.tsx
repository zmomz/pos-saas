import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// #243 AC2 — the MRR hero must not reserve a ~150px dead block under the value
// for the "Trend history not available yet" note. The honest empty-state text
// stays, but it must not balloon the hero into a half-empty surface.

const BASE = 'http://127.0.0.1:8000';

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
      HttpResponse.json({ items: [{ id: 1, company_name: 'Acme', is_active: true, package_type: 5, used_slots: 5 }], total: 1 })
    ),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
      HttpResponse.json({
        total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
        churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05,
        collected: 5000, platform_revenue: 800, by_agent: [],
      })
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

describe('MasterDashboard hero (#243 AC2)', () => {
  it('keeps the honest trend-history note but reserves no 150px dead block', async () => {
    server.use(...baseHandlers());
    renderPage();
    const note = await screen.findByTestId('mrr-trend-note');
    expect(note.className).not.toContain('h-[150px]');
  });
});
