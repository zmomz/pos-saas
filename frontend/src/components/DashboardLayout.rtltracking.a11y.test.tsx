import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset. The sidebar nav-section
// overline labels (e.g. "SELL", "CATALOG") render translated section names in a
// classic Latin `uppercase tracking-wider` treatment. Arabic joins its letters
// cursively, so that tracking shatters the joins under an Arabic/RTL locale. The
// base `[dir='rtl']` reset in index.css lives in @layer base and loses to
// Tailwind's utility layer, so the tracking survives on these labels. The fix
// mirrors the `rtl:rotate-180` icon idiom: an `rtl:tracking-normal` variant that
// neutralises the spacing only under an RTL ancestor, leaving LTR untouched.

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

describe('DashboardLayout nav-section RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on every uppercase section overline label under RTL', () => {
    const { container } = renderShell();
    // Each section header wraps its translated label in a `lg:sr-only` span; the
    // header div itself carries the uppercase/tracking overline treatment.
    const labels = container.querySelectorAll('[class*="lg:sr-only"]');
    expect(labels.length).toBeGreaterThan(0);
    labels.forEach((label) => {
      const header = label.parentElement as HTMLElement;
      expect(header.className).toContain('uppercase');
      expect(header.className).toContain('rtl:tracking-normal');
    });
  });
});
