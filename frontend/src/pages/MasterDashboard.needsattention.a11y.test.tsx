import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// ISSUE-226 (a11y) — keyboard-only nav audit. The "Needs Attention" tiles are
// actionable rows (reactivate a paused agent, add slots, review the global tax
// rate) that were rendered as plain <div onClick> — reachable with a mouse but
// invisible to Tab and inert to Enter/Space. This slice makes each actionable
// row a real, focusable button so a keyboard-only operator can act on it.

const BASE = 'http://127.0.0.1:8000';

function economics() {
  return {
    total_agents: 1, active_agents: 0, total_clients: 0, active_clients: 0,
    churned_clients: 0, mrr: 0, arr: 0, churn_rate: 0,
    collected: 0, platform_revenue: 0, by_agent: [],
  };
}

function baseHandlers(agents: unknown[] = []) {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () => HttpResponse.json({ items: agents, total: agents.length })),
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

describe('MasterDashboard "Needs Attention" keyboard operability (ISSUE-226)', () => {
  it('reactivates a paused agent when its row is activated from the keyboard', async () => {
    let toggled = false;
    server.use(
      ...baseHandlers([
        { id: 7, company_name: 'Acme', email: 'a@x.io', package_type: 5, used_slots: 1, is_active: false },
      ]),
      http.post(`${BASE}/api/v1/tenant/master/agents/7/toggle`, () => {
        toggled = true;
        return HttpResponse.json({ success: true, is_active: true });
      }),
    );
    renderPage();

    const user = userEvent.setup();
    const row = await screen.findByRole('button', { name: /Acme/i });
    row.focus();
    expect(row).toHaveFocus();
    await user.keyboard('{Enter}');

    await waitFor(() => expect(toggled).toBe(true));
  });

  it('opens the add-slots dialog when a near-cap row is activated from the keyboard', async () => {
    server.use(
      ...baseHandlers([
        { id: 9, company_name: 'Zenith', email: 'z@x.io', package_type: 10, used_slots: 10, is_active: true },
      ]),
    );
    renderPage();

    const user = userEvent.setup();
    const row = await screen.findByRole('button', { name: /Zenith/i });
    row.focus();
    await user.keyboard('{Enter}');

    // The slot dialog surfaces the company name in its heading.
    expect(await screen.findByRole('dialog')).toHaveTextContent(/Zenith/i);
  });

  it('opens the global tax-rate dialog when its row is activated from the keyboard', async () => {
    server.use(
      ...baseHandlers([]),
      http.get(`${BASE}/api/v1/tenant/tax-rate`, () =>
        HttpResponse.json({ tax_rate: 15, is_global: true })
      ),
    );
    renderPage();

    const user = userEvent.setup();
    const row = await screen.findByRole('button', { name: /tax rate/i });
    row.focus();
    expect(row).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });
});
