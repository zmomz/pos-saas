import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Screen-reader pass (#226): the global chrome (icon rail + header) carries four
// icon-only controls — theme toggle, language switcher, logout, and the
// notifications bell. Each rendered only a `title`, which is an unreliable
// accessible name for icon-only controls (touch/keyboard-only users and several
// screen readers don't announce it). WCAG 4.1.2 Name, Role, Value wants an
// explicit `aria-label`. This suite pins that contract on every dashboard page.

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

describe('Global chrome icon-only controls carry accessible names (#226)', () => {
  it('gives the logout control an explicit aria-label', () => {
    renderShell();
    const logout = screen.getByRole('button', { name: /logout/i });
    expect(logout).toHaveAttribute('aria-label', 'Logout');
  });

  it('gives the language switcher an explicit aria-label', () => {
    renderShell();
    const lang = screen.getByRole('button', { name: /^language$/i });
    expect(lang).toHaveAttribute('aria-label', 'Language');
  });

  it('gives the notifications bell an explicit aria-label', () => {
    renderShell();
    const bell = screen.getByRole('button', { name: /notifications/i });
    expect(bell).toHaveAttribute('aria-label', 'Notifications');
  });

  it('names the theme toggle for its target mode (dark, in light mode)', () => {
    themeState.isDark = false;
    renderShell();
    const toggle = screen.getByRole('button', { name: /switch to dark mode/i });
    expect(toggle).toHaveAttribute('aria-label', 'Switch to dark mode');
  });

  it('names the theme toggle for its target mode (light, in dark mode)', () => {
    themeState.isDark = true;
    renderShell();
    const toggle = screen.getByRole('button', { name: /switch to light mode/i });
    expect(toggle).toHaveAttribute('aria-label', 'Switch to light mode');
  });

  it('localises the theme-toggle accessible name (Arabic)', () => {
    localStorage.setItem('pos-language', 'ar');
    renderShell();
    // RED under a hardcoded English title: the Arabic name must be present and
    // must not fall back to the English string.
    const toggle = screen.getByRole('button', { name: 'التبديل إلى الوضع الداكن' });
    expect(toggle).toBeInTheDocument();
  });
});
