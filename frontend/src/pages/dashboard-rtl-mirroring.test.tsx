import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';
import ClientDashboard from './ClientDashboard';

// ISSUE-226 (a11y) — RTL layout, page-level slice. The shared shadcn primitives
// were mirrored in an earlier slice; this covers the directional arrows/chevrons
// the dashboards render directly. A "view all" arrow and a drill-in row chevron
// point in the reading direction — unmirrored they point the wrong way under
// Arabic/Urdu. The dashboards' local idiom is Tailwind's `rtl:-scale-x-100`
// (horizontal flip beneath a `[dir="rtl"]` ancestor); accept `rtl:rotate-180`
// too since both mirror a horizontal arrow.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

function masterHandlers() {
  return [
    http.get(`${BASE}/tenant/master/agents`, () =>
      HttpResponse.json({ items: [], total: 0 })
    ),
    http.get(`${BASE}/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/tenant/master/economics`, () =>
      HttpResponse.json({
        total_agents: 0, active_agents: 0, total_clients: 0, active_clients: 0,
        churned_clients: 0, mrr: 0, arr: 0, churn_rate: 0,
        collected: 0, platform_revenue: 0, by_agent: [],
      })
    ),
  ];
}

function clientHandlers() {
  return [
    http.get(`${BASE}/tenant/client/dashboard`, () =>
      HttpResponse.json({ total_sales: 0, today_sales: 0, total_transactions: 0, today_transactions: 0, products_count: 0 })
    ),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/subscription`, () =>
      HttpResponse.json({
        client_id: 1, business_name: 'Falafel House', subscription_fee: 200,
        billing_cycle: 'monthly', subscription_status: 'active',
        next_billing_date: '2026-08-01', is_active: true,
        moyasar_publishable_key: 'pk_test', payments: [],
      })
    ),
  ];
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => { server.resetHandlers(); vi.clearAllMocks(); });
afterAll(() => server.close());

describe('Dashboard RTL directional-arrow mirroring (ISSUE-226)', () => {
  it('mirrors the ClientDashboard "view all" arrow', async () => {
    server.use(...clientHandlers());
    render(
      <MemoryRouter>
        <LanguageProvider>
          <ClientDashboard />
        </LanguageProvider>
      </MemoryRouter>
    );
    const btn = await screen.findByRole('button', { name: /view all/i });
    expect(isMirrored(btn.querySelector('svg'))).toBe(true);
  });

  it('mirrors the MasterDashboard "view all" arrow and drill-in row chevron', async () => {
    server.use(...masterHandlers());
    render(
      <MemoryRouter>
        <LanguageProvider>
          <MasterDashboard />
        </LanguageProvider>
      </MemoryRouter>
    );
    const viewAll = await screen.findByRole('button', { name: /^view all$/i });
    expect(isMirrored(viewAll.querySelector('svg'))).toBe(true);

    // The always-present "Review global tax rate" row: swatch icon + drill-in
    // chevron. The chevron (last svg) must mirror; the swatch must not.
    const taxRow = (await screen.findByText(/review global tax rate/i)).closest('.dxr-insight');
    expect(taxRow).not.toBeNull();
    const icons = taxRow!.querySelectorAll('svg');
    expect(isMirrored(icons[icons.length - 1])).toBe(true);
  });
});
