import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';

// #208 (M11 FE-Platform) — single money/date formatting path. The Recent
// Activity feed's timestamp must render through the shared `formatDateTime`
// helper, not a bespoke `new Date(...).toLocaleString('en-GB', ...)` call.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const CREATED_AT = '2026-03-14T09:05:00Z';

vi.mock('@/lib/api', () => ({
  getMasterAgents: vi.fn().mockResolvedValue({ items: [] }),
  getPackages: vi.fn().mockResolvedValue({ items: [] }),
  getMasterEconomics: vi.fn().mockResolvedValue({ by_agent: [] }),
  getAuditLogs: vi.fn().mockResolvedValue([
    { id: 'a1', user_email: 'op@acme.test', action: 'agent.suspend', details: 'Suspended agent', created_at: '2026-03-14T09:05:00Z' },
  ]),
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

describe('MasterDashboard recent-activity timestamp (#208)', () => {
  it('renders the activity timestamp through the shared formatDateTime path', async () => {
    renderPage();

    // Default language is 'en'. The rendered timestamp must equal the shared
    // helper's output (dd/mm/yyyy, hh:mm) — not the old "Mar 14, 09:05" bespoke
    // toLocaleString format.
    const expected = formatDateTime(CREATED_AT, 'en');
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
});
