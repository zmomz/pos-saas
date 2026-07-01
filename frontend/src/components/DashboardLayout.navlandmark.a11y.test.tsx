import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-226 (a11y · SR audit) — the primary sidebar navigation is a
// `<nav>` landmark, but an unnamed one. Screen-reader users who navigate by
// landmark (rotor / "next landmark") hear a bare "navigation" with nothing to
// distinguish it, and can't jump straight to the app's main nav. WCAG landmark
// practice (ARIA11) says every navigation landmark should carry an accessible
// name. This asserts the rail's <nav> exposes one via aria-label.

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

const themeState = { toggleTheme: vi.fn(), isDark: false };
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => themeState }));

vi.mock('@/lib/api', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api')>();
  return { ...actual, getNotifications: vi.fn().mockResolvedValue({ unread_count: 0 }) };
});

vi.mock('@/components/OnboardingTour', () => ({ default: () => null }));
vi.mock('@/components/states/OfflineBanner', () => ({ default: () => null }));
vi.mock('@/components/dashboard/rx/CommandPalette', () => ({ default: () => null }));

import DashboardLayout from './DashboardLayout';

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/products']}>
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
  themeState.isDark = false;
});

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('DashboardLayout primary-nav landmark name (ISSUE-226)', () => {
  it('names the sidebar navigation landmark for screen readers', () => {
    renderShell();
    // Resolvable by its accessible name — an unnamed <nav> would not match.
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(nav).toBeInTheDocument();
  });
});
