import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { DARK_INK } from '@/lib/contrast';
import AgentDashboard from './AgentDashboard';

// #243 AC2/AC3 — dashboard visual-correctness cluster for the agent surface:
//  • no duplicate in-body header (the shell already renders the page title via
//    usePageChrome; a bespoke <h1> duplicated it and the Run-billing action).
//  • the white-label preview must be a flat fill with a contrast-derived
//    foreground — a same-color `linear-gradient(b, b)` painting hard-coded white
//    text/logo renders them invisible on a pale brand.

const BASE = 'http://127.0.0.1:8000';

function handlers(primaryColor: string) {
  return [
    http.get(`${BASE}/api/v1/tenant/agent/clients`, () =>
      HttpResponse.json({ items: [], total: 0, remaining_slots: 5 })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () =>
      HttpResponse.json({ company_name: 'Pale Co', primary_color: primaryColor })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () =>
      HttpResponse.json({ collected: 0, payments: 0, by_client: [] })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () =>
      HttpResponse.json({
        quota_price: 80, quota_cycle: 'monthly', quota_status: 'active',
        has_card: false, has_moyasar_account: true, payments: [],
      })
    ),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () =>
      HttpResponse.json({ statements: [] })
    ),
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

describe('AgentDashboard visual correctness (#243)', () => {
  it('renders no duplicate in-body <h1> header (the shell owns the title)', async () => {
    server.use(...handlers('#1488a6'));
    renderPage();
    // Wait for the page to finish loading (revenue tile present).
    await screen.findByTestId('wl-preview-header');
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });

  it('flattens the white-label preview to a fill (no same-color gradient)', async () => {
    server.use(...handlers('#1488a6'));
    renderPage();
    const header = await screen.findByTestId('wl-preview-header');
    expect(header.style.background).not.toContain('gradient');
  });

  it('uses dark ink in the preview on a pale brand (white would be invisible)', async () => {
    // #fde68a — pale amber, luminance > 0.6, so white text is unreadable.
    server.use(...handlers('#fde68a'));
    renderPage();
    const header = await screen.findByTestId('wl-preview-header');
    await waitFor(() =>
      expect(header.style.color.replace(/\s/g, '')).toBe('rgb(10,10,10)')
    );
    void DARK_INK; // documents the expected ink source
  });

  it('uses white in the preview on a dark brand', async () => {
    server.use(...handlers('#0b3d4d'));
    renderPage();
    const header = await screen.findByTestId('wl-preview-header');
    await waitFor(() =>
      expect(header.style.color.replace(/\s/g, '')).toBe('rgb(255,255,255)')
    );
  });
});
