import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// ISSUE-023 (H9) — the Remaining-Slots tile must read `remaining_slots`/`total`
// from GET /agent/clients. Previously it computed from `branding.client_slots/
// used_slots`, which BrandingResponse never carries, so it always rendered 0/blank.

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

describe('AgentDashboard remaining-slots tile (ISSUE-023)', () => {
  it('renders the real remaining slots and total capacity from the clients response', async () => {
    server.use(
      // 3 clients occupy slots, 2 remain -> capacity 5.
      http.get(`${BASE}/api/v1/tenant/agent/clients`, () =>
        HttpResponse.json({
          items: [
            { id: 1, business_name: 'A', email: 'a@x.co', phone: '', is_active: true, subscription_fee: 0, zatca_enabled: true },
            { id: 2, business_name: 'B', email: 'b@x.co', phone: '', is_active: true, subscription_fee: 0, zatca_enabled: true },
            { id: 3, business_name: 'C', email: 'c@x.co', phone: '', is_active: false, subscription_fee: 0, zatca_enabled: true },
          ],
          total: 3,
          remaining_slots: 2,
        })
      ),
      http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
      http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 0, payments: 0, by_client: [] })),
      http.get(`${BASE}/api/v1/tenant/agent/quota`, () => HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: false, payments: [] })),
      http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] })),
      // The right-rail feature panel hydrates the default client's real flags.
      http.get(`${BASE}/api/v1/tenant/agent/clients/:clientId/features`, ({ params }) =>
        HttpResponse.json({
          client_id: Number(params.clientId),
          features: { inventory: true, discounts: true, loyalty: true, zatca: true, email_receipts: true },
        })
      )
    );
    renderPage();

    const slotLabel = await screen.findByText('Remaining Slots');
    const tile = slotLabel.parentElement!.parentElement!;
    // remaining (2) out of total capacity (remaining 2 + used 3 = 5).
    expect(tile).toHaveTextContent('2 of 5');
  });
});
