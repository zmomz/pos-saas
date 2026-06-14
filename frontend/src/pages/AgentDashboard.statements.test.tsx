import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// ISSUE-055 — an agent reviews periodic commission statements on the dashboard:
// one statement per billing period with line items by client, summing back to
// the underlying ledger (collected == owed + net).

const BASE = 'http://127.0.0.1:8000';

const STATEMENTS = {
  statements: [
    {
      period_start: '2026-06-01',
      period_end: '2026-07-01',
      billing_cycle: 'monthly',
      collected: 15,
      master_owed: 8,
      net: 7,
      payments: 1,
      by_client: [
        { client_id: 3, business_name: 'Corner Shop', collected: 15, master_owed: 8, net: 7, payments: 1 },
      ],
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AgentDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentDashboard commission statements (ISSUE-055)', () => {
  it('lists per-period statements with client line items', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/clients`, () => HttpResponse.json({ items: [], total: 0, remaining_slots: 5 })),
      http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
      http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 15, master_owed: 8, net: 7, payments: 1, by_client: [] })),
      http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json(STATEMENTS))
    );
    renderPage();

    // The period window heading surfaces, and the client line item is listed.
    expect(await screen.findByText(/2026-06-01/)).toBeInTheDocument();
    const region = screen.getByTestId('commission-statements');
    expect(within(region).getByText('Corner Shop')).toBeInTheDocument();
  });
});
