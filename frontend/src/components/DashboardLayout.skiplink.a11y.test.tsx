import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Keyboard-only nav audit (#226): every back-office page is preceded by a long
// icon rail + header. A keyboard/SR user must be able to bypass those repeated
// blocks and jump straight to the page content (WCAG 2.4.1 Bypass Blocks).

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

describe('Skip to main content link (#226)', () => {
  it('exposes a skip link that targets the main content region', () => {
    renderShell('/products');
    const skip = screen.getByRole('link', { name: /skip to main content/i });
    expect(skip).toHaveAttribute('href', '#main-content');
  });

  it('makes the skip link the first focusable element in the DOM', () => {
    const { container } = renderShell('/products');
    const focusables = container.querySelectorAll('a[href], button, [tabindex]');
    // The very first thing keyboard focus lands on must be the bypass link.
    expect(focusables[0]).toHaveAttribute('href', '#main-content');
  });

  it('points the skip link at a focusable <main> landmark', () => {
    renderShell('/products');
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    // A programmatic-focus target needs an explicit tabindex so the browser
    // moves focus there when the in-page anchor is activated.
    expect(main).toHaveAttribute('tabindex', '-1');
  });
});
