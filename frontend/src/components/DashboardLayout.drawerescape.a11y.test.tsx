import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// Keyboard-only nav audit (#226 · WCAG 2.1.1 Keyboard): the mobile navigation
// drawer slides in from a hamburger toggle and can be dismissed by clicking the
// backdrop — but a backdrop click is a pointer-only affordance. A keyboard user
// who opens the drawer must also be able to dismiss it with Escape, the standard
// dismissal gesture for every other overlay in the app (command palette, dialogs).

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

// The drawer's open/closed state is reflected on the <aside> rail: closed it
// carries the off-canvas `-translate-x-full` transform; open it does not.
const drawer = (container: HTMLElement) =>
  container.querySelector('[data-tour="sidebar-nav"]') as HTMLElement;

describe('Mobile nav drawer — Escape to dismiss (#226)', () => {
  it('closes the open drawer when Escape is pressed', () => {
    const { container } = renderShell('/products');

    // Open the drawer via the hamburger toggle.
    fireEvent.click(screen.getByRole('button', { name: /menu/i }));
    expect(drawer(container).className).not.toContain('-translate-x-full');

    // Escape must dismiss it, matching every other overlay's keyboard contract.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(drawer(container).className).toContain('-translate-x-full');
  });

  it('does not throw when Escape is pressed while the drawer is already closed', () => {
    const { container } = renderShell('/products');
    // Closed on first paint; a stray Escape is a no-op, not an error.
    expect(drawer(container).className).toContain('-translate-x-full');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(drawer(container).className).toContain('-translate-x-full');
  });
});
