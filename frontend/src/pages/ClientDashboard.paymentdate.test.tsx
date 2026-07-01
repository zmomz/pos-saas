import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';
import { formatDate } from '@/lib/format';

// #208 (M11 FE-Platform) — dates through the shared formatDate path. The client
// dashboard's payment-history rows rendered the billing period raw via
// `period_start || created_at.slice(0, 10)`, a bypass that skipped the
// locale-aware Gregorian/Western-numeral formatting the panel's next-billing
// date (and the AgentDashboard payment rows) already use.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const SUBSCRIPTION = {
  subscription_fee: 200,
  subscription_status: 'active',
  billing_cycle: 'monthly',
  next_billing_date: '2026-08-01',
  moyasar_publishable_key: null,
  payments: [
    { id: 11, amount: 200, period_start: '2026-07-01', method: 'sandbox', created_at: '2026-07-01' },
  ],
};

vi.mock('@/lib/api', () => ({
  getClientDashboard: vi.fn().mockResolvedValue({
    today_sales: 0,
    total_sales: 0,
    total_transactions: 0,
    today_transactions: 0,
  }),
  getClientBranding: vi.fn().mockResolvedValue(null),
  getTransactions: vi.fn().mockResolvedValue([]),
  getClientSubscription: vi.fn().mockResolvedValue(SUBSCRIPTION),
  payClientSubscription: vi.fn(),
  saveSubscriptionCard: vi.fn(),
  downloadSubscriptionInvoice: vi.fn(),
  getLowStockProducts: vi.fn().mockResolvedValue(null),
  getTopProducts: vi.fn().mockResolvedValue(null),
  getInventoryReport: vi.fn().mockResolvedValue(null),
  getRestaurantTables: vi.fn().mockResolvedValue(null),
  getKdsTickets: vi.fn().mockResolvedValue(null),
  getReservations: vi.fn().mockResolvedValue(null),
}));

beforeEach(() => {
  window.matchMedia = ((query: string) => ({
    matches: /prefers-reduced-motion/.test(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => vi.restoreAllMocks());

async function renderPage() {
  const { default: ClientDashboard } = await import('./ClientDashboard');
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ClientDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

describe('ClientDashboard payment-history dates (#208)', () => {
  it('renders the billing period through formatDate, not a raw date string', async () => {
    await renderPage();

    // period_start '2026-07-01' localises to '01/07/2026' (en-GB); the raw ISO
    // date must not survive.
    expect(await screen.findByText(formatDate('2026-07-01', 'en'))).toBeInTheDocument();
    expect(screen.queryByText('2026-07-01')).not.toBeInTheDocument();
  });
});
