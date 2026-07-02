import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';

// Login (Index) is the only core-flow page that reads AuthContext directly;
// stub it into a logged-out state so the login form renders without a provider.
const authState = {
  user: null as { role: string } | null,
  loading: false,
  login: vi.fn(),
  register: vi.fn(),
  completeMfaLogin: vi.fn(),
  loginWithPin: vi.fn(),
};
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => authState }));

import Index from './Index';
import POSTerminal from './POSTerminal';
import KDS from './KDS';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-274 (M11 · FE-Platform · a11y) — Automated WCAG gate (axe) on core flows.
//
// Every other a11y slice in this milestone is a hand-written role/name
// assertion; nothing scanned the rendered DOM programmatically, so a fresh WCAG
// regression (an unlabeled control, a duplicate id, a bad ARIA reference) could
// land unseen. This suite runs axe-core over the core-flow pages — POS checkout,
// KDS, Reports, Login — and fails the build on any violation.
//
// Scan config: jsdom performs no layout, so rules that need real geometry
// (`color-contrast`) or full-document landmark structure (`region`) can't be
// evaluated meaningfully here and are disabled — they belong to the Playwright
// e2e layer. Everything else (name/role/value, labels, ARIA validity, duplicate
// ids, list structure, …) runs against the WCAG 2 A/AA tag set.

const BASE = 'http://127.0.0.1:8000/api/v1';

// Shared axe options: WCAG 2.0/2.1 A+AA, minus the two jsdom-incompatible rules.
const AXE_OPTS = {
  runOnly: { type: 'tag' as const, values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  rules: {
    'color-contrast': { enabled: false },
    region: { enabled: false },
  },
};

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
  localStorage.clear();
});
afterAll(() => server.close());

describe('a11y axe gate — the gate actually bites (#274)', () => {
  it('reports violations for markup that breaks WCAG name/role/value', async () => {
    // A button with no accessible name and an <img> with no alt are textbook
    // WCAG 4.1.2 / 1.1.1 failures. If axe is wired correctly this scan must
    // surface at least one violation — proving the gate fails on real problems.
    const el = document.createElement('div');
    el.innerHTML = '<button></button><img src="x.png">';
    const results = await axe(el, AXE_OPTS);
    expect(results.violations.length).toBeGreaterThan(0);
  });

  it('passes clean, well-labelled markup', async () => {
    const el = document.createElement('div');
    el.innerHTML = '<button type="button">Save</button><img src="x.png" alt="Logo">';
    const results = await axe(el, AXE_OPTS);
    expect(results).toHaveNoViolations();
  });
});

function renderWithProviders(node: ReactNode) {
  return render(
    <MemoryRouter>
      <LanguageProvider>{node}</LanguageProvider>
    </MemoryRouter>,
  );
}

describe('a11y axe gate — core flows have no WCAG violations (#274)', () => {
  it('Login (Index) passes axe', async () => {
    const { container } = renderWithProviders(<Index />);
    await screen.findByText(/welcome to pos system/i);
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it('POS checkout passes axe', async () => {
    server.use(
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ is_master: false, denied: [], granted: [] }),
      ),
      http.get(`${BASE}/entities/customers`, () => HttpResponse.json([{ id: 1, name: 'Sara' }])),
      http.get(`${BASE}/entities/branches`, () => HttpResponse.json([{ id: 2, name: 'Downtown' }])),
      http.get(`${BASE}/entities/products`, () => HttpResponse.json([])),
      http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
      http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/pos/transactions`, () => HttpResponse.json({ items: [] })),
      http.get(`${BASE}/tenant/client/branding`, () =>
        HttpResponse.json({
          company_name: 'Test Shop',
          primary_color: '#000',
          secondary_color: '#fff',
          font_family: 'sans',
          button_radius: '0.5rem',
        }),
      ),
    );
    const { container } = renderWithProviders(<POSTerminal />);
    await screen.findByRole('combobox', { name: /select customer/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it('KDS passes axe', async () => {
    server.use(
      http.get(`${BASE}/restaurant/kds/stations`, () =>
        HttpResponse.json([{ id: 1, name: 'Grill', name_ar: 'الشواية' }]),
      ),
      http.get(`${BASE}/restaurant/kds/tickets`, () => HttpResponse.json({ items: [], total: 0 })),
    );
    const { container } = renderWithProviders(<KDS />);
    await screen.findByRole('button', { name: /all stations/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it('Reports passes axe', async () => {
    // Settle every report fetch (500 → error branch) so the page reaches its
    // loaded chrome, then scan.
    server.use(http.get(`${BASE}/*`, () => new HttpResponse(null, { status: 500 })));
    const { container } = renderWithProviders(<ReportsAnalytics />);
    await waitFor(() => {
      expect(screen.getByRole('status')).not.toHaveTextContent(/loading/i);
    });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });
});
