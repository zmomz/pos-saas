import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// #235 (AC3) — an unconnected Moyasar blocks the agent's whole merchant book.
// The agent's own dashboard must surface that fail-closed state prominently,
// not bury it in a small status pill.

const BASE = 'http://127.0.0.1:8000';

function handlers(hasMoyasar: boolean) {
  return [
    http.get(`${BASE}/api/v1/tenant/agent/clients`, () => HttpResponse.json({ items: [], total: 0, remaining_slots: 5 })),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 0, payments: 0, by_client: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () =>
      HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: hasMoyasar, payments: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/clients/:clientId/features`, ({ params }) =>
      HttpResponse.json({ client_id: Number(params.clientId), features: {} })
    ),
  ];
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

describe('AgentDashboard Moyasar fail-closed banner (#235)', () => {
  it('shows the prominent banner when the agent has not connected Moyasar', async () => {
    server.use(...handlers(false));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('agent-moyasar-banner')).toBeInTheDocument());
  });

  it('hides the banner once the agent has connected Moyasar', async () => {
    server.use(...handlers(true));
    renderPage();
    // Quota resolves; the connected pill is shown and no fail-closed banner.
    await waitFor(() => expect(screen.getAllByText(/connected/i).length).toBeGreaterThan(0));
    expect(screen.queryByTestId('agent-moyasar-banner')).not.toBeInTheDocument();
  });
});
