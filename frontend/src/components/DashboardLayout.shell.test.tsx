import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Shell IA (issue #213): the nav rail is sectioned (Sell / Catalog / People /
// Setup), page identity is promoted to an H1 with the greeting demoted to the
// dashboard home only, the mobile drawer shows text labels, and reused icons
// (Receipt, Package) are de-duplicated.

const authState = {
  user: { role: 'client', name: 'Zeyad', email: 'z@b.com' } as
    | { role: string; name?: string; email?: string }
    | null,
  logout: vi.fn(),
};

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => authState }));

const businessState = { businessType: 'both' as string | null };
vi.mock('@/contexts/BusinessProfileContext', () => ({
  useBusinessProfile: () => businessState,
}));

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ toggleTheme: vi.fn(), isDark: false }),
}));

vi.mock('@/lib/api', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api')>();
  return { ...actual, getNotifications: vi.fn().mockResolvedValue({ unread_count: 0 }) };
});

vi.mock('@/components/OnboardingTour', () => ({ default: () => null }));
vi.mock('@/components/states/OfflineBanner', () => ({ default: () => null }));
vi.mock('@/components/dashboard/rx/CommandPalette', () => ({ default: () => null }));

import DashboardLayout, { navConfig } from './DashboardLayout';

function renderShell(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LanguageProvider>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route path="client" element={<div>home</div>} />
            <Route path="products" element={<div>products page</div>} />
          </Route>
        </Routes>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.setItem('pos-language', 'en');
  authState.user = { role: 'client', name: 'Zeyad', email: 'z@b.com' };
  businessState.businessType = 'both';
});

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('Shell IA — sectioned rail (#213)', () => {
  it('groups the client rail under Sell / Catalog / People / Setup headers', () => {
    renderShell('/client');
    const nav = screen.getByRole('navigation');
    expect(within(nav).getByText('Sell')).toBeInTheDocument();
    expect(within(nav).getByText('Catalog')).toBeInTheDocument();
    expect(within(nav).getByText('People')).toBeInTheDocument();
    expect(within(nav).getByText('Setup')).toBeInTheDocument();
  });
});

describe('Shell IA — page identity vs greeting (#213)', () => {
  it('shows the greeting on the dashboard home', () => {
    renderShell('/client');
    expect(screen.getByText(/Good (morning|afternoon|evening), Zeyad/)).toBeInTheDocument();
  });

  it('shows the page H1 and hides the greeting off the dashboard home', () => {
    renderShell('/products');
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1).toHaveTextContent('Products');
    expect(screen.queryByText(/Good (morning|afternoon|evening)/)).not.toBeInTheDocument();
  });
});

describe('Shell IA — mobile drawer labels (#213)', () => {
  it('renders a visible text label next to each rail icon', () => {
    renderShell('/client');
    const link = screen.getByRole('link', { name: 'Products' });
    // aria-label alone would not add text content; a real label node must exist.
    expect(link).toHaveTextContent('Products');
  });
});

describe('Shell IA — de-duplicated icons (#213)', () => {
  for (const role of ['master', 'agent', 'client'] as const) {
    it(`uses a distinct icon for every ${role} rail item`, () => {
      const items = navConfig[role].flatMap((section) => section.items);
      const icons = items.map((item) => item.icon);
      expect(new Set(icons).size).toBe(icons.length);
    });
  }
});
