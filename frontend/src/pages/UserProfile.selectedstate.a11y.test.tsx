import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AccessibilityProvider } from '@/contexts/AccessibilityContext';
import UserProfile from './UserProfile';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the UserProfile
// settings page's single-select button groups.
//
// The Language picker (English / العربية / …) and the Theme picker (Light /
// Dark) each signalled their ACTIVE member with colour classes only (the
// `default` button variant — a filled brand background). A screen-reader user
// tabbing either group heard each option's label but never WHICH one was
// currently selected — WCAG 1.4.1 (use-of-colour) / 4.1.2 (name, role, value).
// The sibling Accessibility group on the same page (high-contrast + font-scale)
// already exposes `aria-pressed`; these two lagged behind. This slice brings
// them onto the same toggle-button convention.

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
beforeEach(() =>
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
  )
);
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile selected-state a11y (#226)', () => {
  it('exposes the active language via aria-pressed', async () => {
    renderPage();

    // Default language is English; each option is a toggle button.
    const english = await screen.findByRole('button', { name: 'English' });
    const arabic = screen.getByRole('button', { name: 'العربية' });

    expect(english).toHaveAttribute('aria-pressed', 'true');
    expect(arabic).toHaveAttribute('aria-pressed', 'false');
  });

  it('moves aria-pressed when a different language is chosen', async () => {
    const user = userEvent.setup();
    renderPage();

    const arabic = await screen.findByRole('button', { name: 'العربية' });
    expect(arabic).toHaveAttribute('aria-pressed', 'false');

    await user.click(arabic);

    // After switching, the Arabic option is the selected member. (The English
    // label re-renders under the new locale, so re-query by pressed state.)
    await waitFor(() => expect(arabic).toHaveAttribute('aria-pressed', 'true'));
  });

  it('exposes the active theme via aria-pressed', async () => {
    const user = userEvent.setup();
    renderPage();

    // Light is the canonical default theme.
    const light = await screen.findByRole('button', { name: /light/i });
    const dark = screen.getByRole('button', { name: /dark/i });

    expect(light).toHaveAttribute('aria-pressed', 'true');
    expect(dark).toHaveAttribute('aria-pressed', 'false');

    await user.click(dark);

    await waitFor(() => expect(dark).toHaveAttribute('aria-pressed', 'true'));
    expect(light).toHaveAttribute('aria-pressed', 'false');
  });
});
