import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset, extended to the
// platform-economics agent-leaderboard column-header row. Its headers (Agent /
// Merchants / MRR / Share / Status) render translated labels under the same
// classic Latin `uppercase tracking-wider` overline treatment carried on the
// header <tr>. Arabic joins its letters cursively, so that tracking shatters the
// joins under an Arabic/RTL locale; the base `[dir='rtl']` reset in index.css
// lives in @layer base and loses to Tailwind's utility layer. This mirrors the
// `rtl:tracking-normal` idiom already applied to the sidebar nav-section, the
// ⌘K group headings, the ForecastInsights stat overlines, and the audit-log
// column headers (#226).

const BASE = 'http://127.0.0.1:8000';

function handlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () =>
      HttpResponse.json({
        total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
        churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05,
        ltv: 8000, cac: null, collected: 5000, platform_revenue: 800,
        by_agent: [
          {
            agent_id: 1, company_name: 'Acme Partners', is_active: true,
            total_clients: 4, active_clients: 3, mrr: 1200, collected: 5000,
            quota_paid: 800, payments: 5000,
          },
        ],
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

describe('MasterDashboard leaderboard-header RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on the uppercase leaderboard column-header row under RTL', async () => {
    server.use(...handlers());
    const { container } = renderPage();

    // The leaderboard table renders once economics resolves with ≥1 agent.
    await screen.findByRole('table');
    const headerRow = container.querySelector('thead tr');
    expect(headerRow).not.toBeNull();
    expect(headerRow!.className).toContain('uppercase');
    expect(headerRow!.className).toContain('tracking-wider');
    // Non-color, RTL-only reset so Arabic joins aren't shattered.
    expect(headerRow!.className).toContain('rtl:tracking-normal');
  });
});
