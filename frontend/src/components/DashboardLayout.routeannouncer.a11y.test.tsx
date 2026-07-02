import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Screen-reader pass (#226 · WCAG 2.4.x): a client-side navigation swaps the
// <main> content without a full page load, so a screen reader is never told the
// page changed. The dashboard shell mounts a persistent polite live region that
// narrates the new page's name on every in-app route change.

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

function GoTo({ to, label }: { to: string; label: string }) {
  const navigate = useNavigate();
  return <button onClick={() => navigate(to)}>{label}</button>;
}

function renderShell(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LanguageProvider>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route path="products" element={<GoTo to="/reports" label="jump reports" />} />
            <Route path="reports" element={<div>reports page</div>} />
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

describe('SPA route announcer (#226)', () => {
  it('mounts a polite live region that is silent on first paint', () => {
    renderShell('/products');
    const region = screen.getByTestId('route-announcer');
    expect(region).toHaveAttribute('aria-live', 'polite');
    // No premature announcement on the initial page load.
    expect(region.textContent).toBe('');
  });

  it('announces the destination page name after an in-app navigation', async () => {
    renderShell('/products');
    await userEvent.click(screen.getByRole('button', { name: 'jump reports' }));
    await waitFor(() =>
      expect(screen.getByTestId('route-announcer').textContent).toBe('Reports & Analytics')
    );
  });
});
