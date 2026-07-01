import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AccessibilityProvider } from '@/contexts/AccessibilityContext';
import UserProfile from './UserProfile';

// M11 · FE-Platform a11y (#226) — the "Reduce motion" mode surfaced in the
// UserProfile Accessibility panel, alongside high-contrast and font-scale.
//
// Some viewers cannot (or have not) set the OS-level `prefers-reduced-motion`
// preference — e.g. a cashier on a shared POS terminal. This in-app toggle lets
// them still animations/transitions app-wide by adding a `reduce-motion` class
// to <html> (see AccessibilityContext + index.css). The control is a toggle
// button exposing its state via aria-pressed (WCAG 4.1.2), matching the
// sibling high-contrast toggle on the same panel.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PREFS_URL = `${BASE}/users/preferences`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ThemeProvider>
          <AccessibilityProvider>
            <UserProfile />
          </AccessibilityProvider>
        </ThemeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => {
  document.documentElement.className = '';
  localStorage.clear();
  server.use(
    http.get(`${BASE}/auth/sessions`, () => HttpResponse.json({ sessions: [] })),
    http.get(`${BASE}/auth/mfa/status`, () =>
      HttpResponse.json({ enabled: false, recovery_codes_remaining: 0 })
    ),
    http.get(`${BASE}/users/profile`, () =>
      HttpResponse.json({ id: 'u1', email: 'me@b.com', name: 'Me', phone: '', role: 'user' })
    ),
    http.get(PREFS_URL, () =>
      HttpResponse.json({
        display_name: '',
        notification_prefs: {
          email_alerts: true,
          low_stock_alerts: true,
          daily_summary: true,
          transaction_alerts: true,
        },
      })
    )
  );
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile reduce-motion a11y (#226)', () => {
  it('renders an off-by-default Reduce motion toggle exposing aria-pressed', async () => {
    renderPage();

    const reduce = await screen.findByRole('button', { name: /reduce motion/i });
    expect(reduce).toHaveAttribute('aria-pressed', 'false');
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(false);
  });

  it('toggles the reduce-motion mode on and applies the root class', async () => {
    const user = userEvent.setup();
    renderPage();

    const reduce = await screen.findByRole('button', { name: /reduce motion/i });
    await user.click(reduce);

    await waitFor(() => expect(reduce).toHaveAttribute('aria-pressed', 'true'));
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(true);
    expect(localStorage.getItem('pos_a11y_reduce_motion')).toBe('true');
  });
});
