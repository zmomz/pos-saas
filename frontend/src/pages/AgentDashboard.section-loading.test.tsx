import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// #208 (M11 FE-Platform) — states adoption. The in-body section loaders
// (revenue, commission statements, quota, client feature panel) must use the
// shared `LoadingState` (aria-live status region), not bespoke `animate-pulse`
// text blocks. Each section stays loading while its own call is in flight,
// even after the page shell (merchant book) has rendered.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/lib/api', () => ({
  getAgentClients: vi.fn().mockResolvedValue({
    items: [
      {
        id: 1,
        business_name: 'Acme',
        email: 'a@acme.test',
        phone: '',
        is_active: true,
        subscription_fee: 0,
        zatca_enabled: false,
        archived_at: null,
      },
    ],
    remaining_slots: 5,
    total: 1,
  }),
  getAgentBranding: vi.fn().mockResolvedValue(null),
  // In-flight section calls — keep their sections in the loading state.
  getAgentRevenue: vi.fn(() => new Promise(() => {})),
  getAgentCommissionStatements: vi.fn(() => new Promise(() => {})),
  getQuotaStatus: vi.fn(() => new Promise(() => {})),
  getClientFeatures: vi.fn(() => new Promise(() => {})),
  getAgentDashboardKpis: vi.fn(() => new Promise(() => {})),
  createNewClient: vi.fn(),
  toggleClient: vi.fn(),
  setClientZatca: vi.fn(),
  setClientFeature: vi.fn(),
  resetClientPassword: vi.fn(),
  runDunning: vi.fn(),
  payQuota: vi.fn(),
  saveQuotaCard: vi.fn(),
  saveAgentMoyasarKeys: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
  transferClient: vi.fn(),
  exportClientData: vi.fn(),
  deleteClient: vi.fn(),
}));

import AgentDashboard from './AgentDashboard';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AgentDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('AgentDashboard section loading states (#208)', () => {
  it('renders shared LoadingState status regions for in-flight sections, with no bespoke animate-pulse blocks', async () => {
    const { container } = renderPage();

    // Merchant book resolved (top-level loading cleared): the client row renders.
    await screen.findAllByText('Acme');

    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
    // revenue + statements + quota + client-feature panel = four section loaders.
    expect(screen.getAllByRole('status').length).toBeGreaterThanOrEqual(4);
  });
});
