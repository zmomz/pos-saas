import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// M8 / issue-215 — the agent's merchant book exposes archive/restore. The active
// table and the archived table are separate views (KPIs always reflect the live
// book); restoring an archived merchant calls the restore endpoint.

const BASE = 'http://127.0.0.1:8000';

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

describe('AgentDashboard merchant lifecycle (issue-215)', () => {
  it('switches to the archived view and restores an archived merchant', async () => {
    const restore = vi.fn();
    server.use(
      // The clients endpoint splits by the `archived` query param.
      http.get(`${BASE}/api/v1/tenant/agent/clients`, ({ request }) => {
        const archived = new URL(request.url).searchParams.get('archived') === 'true';
        return HttpResponse.json(
          archived
            ? {
                items: [
                  { id: 9, business_name: 'Old Shop', email: 'old@x.co', phone: '', is_active: false, subscription_fee: 50, zatca_enabled: true, language_preference: 'en', archived_at: '2026-01-01T00:00:00+00:00' },
                ],
                total: 1,
                remaining_slots: 4,
              }
            : {
                items: [
                  { id: 1, business_name: 'Live Shop', email: 'live@x.co', phone: '', is_active: true, subscription_fee: 100, zatca_enabled: true, language_preference: 'en', archived_at: null },
                ],
                total: 1,
                remaining_slots: 4,
              }
        );
      }),
      http.post(`${BASE}/api/v1/tenant/agent/clients/9/restore`, () => {
        restore();
        return HttpResponse.json({ success: true, client_id: 9, archived_at: null });
      }),
      http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
      http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 0, payments: 0, by_client: [] })),
      http.get(`${BASE}/api/v1/tenant/agent/quota`, () => HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: false, payments: [] })),
      http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] }))
    );
    renderPage();

    // Live book shows the active merchant (name also echoes in the feature rail).
    expect((await screen.findAllByText('Live Shop')).length).toBeGreaterThan(0);

    // Switch to the Archived tab.
    fireEvent.click(screen.getByRole('tab', { name: 'Archived' }));

    // The archived merchant appears with a Restore action.
    expect(await screen.findByText('Old Shop')).toBeInTheDocument();
    const restoreBtn = await screen.findByTitle('Restore merchant');
    fireEvent.click(restoreBtn);

    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
  });
});
