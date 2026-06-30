import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// H4 (#204) — the agent's merchant-book headline (slots/clients) must not show a
// fabricated all-zero state when its clients fetch fails. A failed
// `/tenant/agent/clients` shows an ErrorState + retry instead.

const BASE = 'http://127.0.0.1:8000';

function secondaryHandlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 0, payments: 0, by_client: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () =>
      HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: false, payments: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] })),
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

describe('AgentDashboard load-failure honesty (H4)', () => {
  it('shows an error+retry instead of a zero merchant book when clients fail', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/clients`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 })
      ),
      ...secondaryHandlers()
    );

    renderPage();

    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    // The white-label headline pill (rendered only by the real dashboard) is gone.
    expect(screen.queryByText(/white-label active/i)).not.toBeInTheDocument();
  });

  it('retry refetches the merchant book once the server recovers', async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/clients`, () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json({ items: [], total: 0, remaining_slots: 4 });
      }),
      ...secondaryHandlers()
    );

    renderPage();

    await screen.findByRole('button', { name: /retry/i });
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    // The honest error state is replaced by the real (empty) merchant book.
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(document.querySelector('[data-tour="stats-section"]')).toBeInTheDocument();
  });
});
