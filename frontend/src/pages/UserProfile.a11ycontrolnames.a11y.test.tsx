import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AccessibilityProvider } from '@/contexts/AccessibilityContext';
import UserProfile from './UserProfile';

// M11 · FE-Platform a11y (#226) — screen-reader names for the Accessibility
// panel controls in UserProfile.
//
// The high-contrast toggle rendered only "On"/"Off" as its label, so a screen
// reader announced "On, button, pressed" with no indication of *what* was on
// (WCAG 4.1.2 Name/Role/Value) — unlike the sibling reduce-motion toggle, which
// carries an explicit aria-label. The three text-size buttons (Normal / Large /
// Extra large) likewise sat in an unlabelled container, so their shared purpose
// ("Text size") was not conveyed. This pass names both.

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

describe('UserProfile a11y control names (#226)', () => {
  it('names the high-contrast toggle beyond its On/Off text and exposes aria-pressed', async () => {
    renderPage();

    const hc = await screen.findByRole('button', { name: /high contrast/i });
    expect(hc).toHaveAttribute('aria-pressed', 'false');
  });

  it('toggles high contrast on and applies the root class', async () => {
    const user = userEvent.setup();
    renderPage();

    const hc = await screen.findByRole('button', { name: /high contrast/i });
    await user.click(hc);

    await waitFor(() => expect(hc).toHaveAttribute('aria-pressed', 'true'));
    expect(document.documentElement.classList.contains('hc')).toBe(true);
    expect(localStorage.getItem('pos_a11y_high_contrast')).toBe('true');
  });

  it('groups the text-size buttons under an accessible "Text size" group name', async () => {
    renderPage();

    // Wait for the panel to render, then find the labelled group.
    await screen.findByRole('button', { name: /high contrast/i });
    const group = screen.getByRole('group', { name: /text size/i });

    const normal = within(group).getByRole('button', { name: /normal/i });
    const large = within(group).getByRole('button', { name: /^large/i });
    const xlarge = within(group).getByRole('button', { name: /extra large/i });

    // Default is "normal": exactly it is pressed.
    expect(normal).toHaveAttribute('aria-pressed', 'true');
    expect(large).toHaveAttribute('aria-pressed', 'false');
    expect(xlarge).toHaveAttribute('aria-pressed', 'false');
  });
});
