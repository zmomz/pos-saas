import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The dashboard
// shell's sign-out control uses the lucide `LogOut` glyph — a door with an arrow
// exiting toward the reading edge (rightwards in LTR). A lucide icon is an inline
// SVG the browser does NOT flip under `[dir="rtl"]`, so an Arabic/Urdu reader (who
// scans right-to-left) sees the exit arrow point *into* the app rather than out of
// it. Per Material Design bidirectionality the logout/exit icon is mirrored in RTL;
// the dashboards' idiom is Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180`).

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

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
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

describe('DashboardLayout logout-icon RTL mirroring (ISSUE-226)', () => {
  it('mirrors the sign-out door/arrow glyph so it exits toward the reading edge', () => {
    renderShell();
    // The sign-out control is named by its `aria-label`/`title` (t('logout')).
    const logout = screen.getByRole('button', { name: /log ?out|sign ?out/i });
    expect(isMirrored(logout.querySelector('svg'))).toBe(true);
  });
});
