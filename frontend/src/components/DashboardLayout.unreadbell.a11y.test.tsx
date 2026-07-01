import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Screen-reader / color-blind pass (#226): the notifications bell surfaces its
// unread state with a small red dot ONLY — a color-only cue with no text or
// programmatic equivalent (WCAG 1.4.1 Use of Color, 4.1.2 Name Role Value).
// A screen-reader or color-blind user hears "Notifications, button" and cannot
// perceive that items are waiting. The bell's accessible name must fold the
// unread count in when there is one, and stay the bare label when there isn't.

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

const notifState = { unread_count: 0 };
vi.mock('@/lib/api', async (importActual) => {
  const actual = await importActual<typeof import('@/lib/api')>();
  return { ...actual, getNotifications: vi.fn().mockImplementation(() => Promise.resolve(notifState)) };
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
  notifState.unread_count = 0;
});

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('Notifications bell exposes its unread state to assistive tech (#226)', () => {
  it('keeps the bare "Notifications" name when nothing is unread', async () => {
    notifState.unread_count = 0;
    renderShell();
    const bell = await screen.findByRole('button', { name: /notifications/i });
    expect(bell).toHaveAttribute('aria-label', 'Notifications');
  });

  it('folds the unread count into the accessible name when items are waiting', async () => {
    notifState.unread_count = 3;
    renderShell();
    // The count-bearing name only appears after the async fetch resolves.
    const bell = await screen.findByRole('button', { name: /3 unread/i });
    const label = bell.getAttribute('aria-label') || '';
    // Still names the control AND surfaces the count — the red dot alone is
    // color-only and invisible to SR/color-blind users.
    expect(label).toMatch(/notifications/i);
    expect(label).toMatch(/3 unread/i);
  });

  it('localises the unread name (Arabic)', async () => {
    localStorage.setItem('pos-language', 'ar');
    notifState.unread_count = 2;
    renderShell();
    // Match on the count-bearing name so we wait for the async fetch, not the
    // bare base label (which appears immediately).
    const bell = await screen.findByRole('button', { name: /غير مقروءة/ });
    const label = bell.getAttribute('aria-label') || '';
    expect(label).toContain('الإشعارات');
    // Must not fall back to the English "unread" string.
    expect(label).not.toMatch(/unread/i);
    expect(label).toContain('2');
  });
});
