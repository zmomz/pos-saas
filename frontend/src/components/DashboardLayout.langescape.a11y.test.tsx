import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Keyboard-only nav audit (#226 · WCAG 2.1.1 Keyboard): the sidebar language
// menu opens from a Globe toggle and can be dismissed by clicking the invisible
// full-screen backdrop — but a backdrop click is a pointer-only affordance. A
// keyboard user who opens the menu must also be able to dismiss it with Escape,
// the standard dismissal gesture every other overlay in the app already honours
// (command palette, dialogs, the mobile nav drawer).

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

import DashboardLayout from './DashboardLayout';

function renderShell(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LanguageProvider>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
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

// The menu is open iff one of its language option buttons is in the DOM. The
// trigger's accessible name is "Language" (a Globe icon), so "English" only
// matches the option, never the toggle.
const openMenu = () => fireEvent.click(screen.getByRole('button', { name: /language/i }));

describe('Sidebar language menu — Escape to dismiss (#226)', () => {
  it('closes the open language menu when Escape is pressed', () => {
    renderShell('/products');

    openMenu();
    expect(screen.getByRole('button', { name: 'English' })).toBeInTheDocument();

    // Escape must dismiss it, matching every other overlay's keyboard contract.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: 'English' })).not.toBeInTheDocument();
  });

  it('does not throw when Escape is pressed while the menu is already closed', () => {
    renderShell('/products');
    // Closed on first paint; a stray Escape is a no-op, not an error.
    expect(screen.queryByRole('button', { name: 'English' })).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: 'English' })).not.toBeInTheDocument();
  });
});
