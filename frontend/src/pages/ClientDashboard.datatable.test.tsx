import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// ISSUE-208 (M11 FE-Platform) — the dashboard "Recent Transactions" list must
// speak the one shared table voice: the `.dxr-tbl` primitive (<DataTable>), not
// a bespoke hand-rolled `<table className="w-full text-sm">`. Column semantics
// (invoice, formatted total, payment method, status) must survive the migration.

const BASE = 'http://127.0.0.1:8000/api/v1';

const ONE_TX = [
  {
    id: 1,
    invoice_number: 'INV-0001',
    total_amount: 125.5,
    payment_method: 'cash',
    created_at: '2026-07-01T10:00:00Z',
  },
];

function baseHandlers(transactions: unknown = ONE_TX) {
  return [
    http.get(`${BASE}/tenant/client/dashboard`, () =>
      HttpResponse.json({ today_sales: 0, today_transactions: 0, total_products: 0, low_stock_count: 0 })
    ),
    http.get(`${BASE}/tenant/client/branding`, () => HttpResponse.json(null)),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json(transactions)),
    http.get(`${BASE}/tenant/client/subscription`, () => HttpResponse.json(null)),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ClientDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ClientDashboard recent-transactions shared table voice (ISSUE-208)', () => {
  it('renders the recent transactions through the shared .dxr-tbl primitive', async () => {
    server.use(...baseHandlers());

    const { container } = renderPage();

    // The row's invoice number proves the list rendered.
    expect(await screen.findByText('INV-0001')).toBeInTheDocument();

    // One shared table voice: the DataTable renders <table class="dxr-tbl">,
    // and there must be no bespoke hand-rolled `text-sm` table left behind.
    expect(container.querySelector('table.dxr-tbl')).toBeInTheDocument();
    expect(container.querySelector('table.text-sm')).not.toBeInTheDocument();
  });

  it('preserves the formatted total and payment-method cells after the migration', async () => {
    server.use(...baseHandlers());

    renderPage();

    // Total is money-formatted (not a raw "125.5"); payment method survives.
    expect(await screen.findByText('INV-0001')).toBeInTheDocument();
    expect(screen.queryByText('125.5')).not.toBeInTheDocument();
    expect(screen.getByText(/125\.50/)).toBeInTheDocument();
    expect(screen.getByText('cash')).toBeInTheDocument();
  });
});
