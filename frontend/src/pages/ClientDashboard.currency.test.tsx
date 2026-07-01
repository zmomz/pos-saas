import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';
import { RIYAL } from '@/lib/format';

// #208 (M11 FE-Platform) — one money formatting path. The client dashboard's
// headline sales KPIs used to render currency through a bespoke `curProps`
// (`<CountUp prefix="⃁ " />`) that placed the symbol *before* the number and
// bypassed `formatMoney` entirely. Currency must flow through `formatMoney`
// (trailing riyal sign, grouped) like every other money value on the page.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

// Resolve the one hard dependency (dashboard stats) with distinctive money
// values; everything else degrades to empty so the KPIs render.
vi.mock('@/lib/api', () => ({
  getClientDashboard: vi.fn().mockResolvedValue({
    today_sales: 1234,
    total_sales: 5678,
    total_transactions: 42,
    today_transactions: 7,
  }),
  getClientBranding: vi.fn().mockResolvedValue(null),
  getTransactions: vi.fn().mockResolvedValue([]),
  getClientSubscription: vi.fn().mockResolvedValue(null),
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

// Force prefers-reduced-motion so CountUp renders the final value synchronously.
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

describe('ClientDashboard currency formatting (#208)', () => {
  it('renders headline sales through formatMoney (trailing riyal), not a leading prefix', async () => {
    const { container } = await renderPage();

    // Today's sales hero + all-time total both go through formatMoney now.
    expect(await screen.findByText(`1,234 ${RIYAL}`)).toBeInTheDocument();
    expect(await screen.findByText(`5,678 ${RIYAL}`)).toBeInTheDocument();

    // No leading-symbol bypass survives (`⃁ 1,234`).
    expect(container.textContent).not.toMatch(new RegExp(`${RIYAL}\\s*1,234`));
  });
});
