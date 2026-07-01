import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// #208 (M11 FE-Platform) — states adoption. The in-page "Revenue by Agent"
// economics loader must use the shared `LoadingState` (aria-live status region),
// not a bespoke `animate-pulse` text block. The section stays loading while the
// economics call is in flight even after the page shell has rendered.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/lib/api', () => ({
  getMasterAgents: vi.fn().mockResolvedValue({ items: [] }),
  getPackages: vi.fn().mockResolvedValue({ items: [] }),
  // Never resolves — keeps `ecoLoading` true so the section loader renders.
  getMasterEconomics: vi.fn().mockReturnValue(new Promise(() => {})),
  getAuditLogs: vi.fn().mockResolvedValue([]),
  getBackupHealth: vi.fn().mockResolvedValue(null),
  toggleAgent: vi.fn(),
  createAgent: vi.fn(),
  addAgentSlots: vi.fn(),
  getTaxRate: vi.fn().mockResolvedValue({ tax_rate: 15 }),
  setGlobalTaxRate: vi.fn(),
  getAgentSuspendImpact: vi.fn(),
}));

import MasterDashboard from './MasterDashboard';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MasterDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('MasterDashboard economics section loading (#208)', () => {
  it('renders the shared LoadingState (status region) for the loading economics section, not a bespoke animate-pulse block', async () => {
    const { container } = renderPage();

    // Page shell has rendered (top-level loading cleared) but economics is in flight.
    const heading = await screen.findByText('Revenue by Agent');
    const section = heading.closest('section') ?? container;

    expect(within(section as HTMLElement).getByRole('status')).toBeInTheDocument();
    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
    });
  });
});
