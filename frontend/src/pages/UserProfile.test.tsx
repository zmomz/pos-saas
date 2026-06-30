import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import UserProfile from './UserProfile';

// ISSUE-078 — per-user profile + notification preferences are persisted
// server-side (no longer localStorage-only), so they follow the user across
// devices. The page loads them from the API on mount and PUTs them on save.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PREFS_URL = `${BASE}/users/preferences`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ThemeProvider>
          <UserProfile />
        </ThemeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
// The security section reads the real current session on mount.
beforeEach(() =>
  server.use(http.get(`${BASE}/auth/sessions`, () => HttpResponse.json({ sessions: [] })))
);
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile server persistence', () => {
  it('loads the persisted profile from the server on mount', async () => {
    server.use(
      http.get(PREFS_URL, () =>
        HttpResponse.json({
          display_name: 'Front Counter',
          notification_prefs: {
            email_alerts: false,
            low_stock_alerts: true,
            daily_summary: true,
            transaction_alerts: false,
          },
        })
      )
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('Your name')).toHaveValue('Front Counter')
    );
  });

  it('saves the profile to the server via PUT', async () => {
    let putBody: any = null;
    server.use(
      http.get(PREFS_URL, () =>
        HttpResponse.json({
          display_name: '',
          notification_prefs: {
            email_alerts: true,
            low_stock_alerts: true,
            daily_summary: false,
            transaction_alerts: true,
          },
        })
      ),
      http.put(PREFS_URL, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json(putBody);
      })
    );

    renderPage();
    const nameInput = await screen.findByPlaceholderText('Your name');

    const user = userEvent.setup();
    await user.type(nameInput, 'Cashier 1');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody.display_name).toBe('Cashier 1');
    expect(putBody.notification_prefs).toMatchObject({
      email_alerts: true,
      transaction_alerts: true,
    });
  });
});
