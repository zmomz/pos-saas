import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import UserProfile from './UserProfile';

// ISSUE-097 — the atoms.dev "Change Password — managed by authentication
// provider" placeholder is gone; now that auth is local the Security card
// exposes a real change-password control wired to POST /users/change-password.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PREFS_URL = `${BASE}/users/preferences`;
const CHANGE_URL = `${BASE}/users/change-password`;

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
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Every test needs the on-mount preferences + sessions fetches satisfied.
function stubPrefs() {
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
          daily_summary: false,
          transaction_alerts: true,
        },
      })
    )
  );
}

describe('UserProfile change-password control', () => {
  it('no longer shows the atoms.dev "managed by auth provider" placeholder', async () => {
    stubPrefs();
    renderPage();

    await screen.findByPlaceholderText('Your name');

    expect(screen.queryByText(/managed by authentication provider/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /via auth provider/i })).toBeNull();
  });

  it('posts the current + new password to the local change-password endpoint', async () => {
    stubPrefs();
    let body: any = null;
    server.use(
      http.post(CHANGE_URL, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: 'ok' });
      })
    );

    renderPage();
    await screen.findByPlaceholderText('Your name');

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText('Current password'), 'OldPass123');
    await user.type(screen.getByPlaceholderText('New password'), 'NewPass123');
    await user.type(screen.getByPlaceholderText('Confirm new password'), 'NewPass123');
    await user.click(screen.getByRole('button', { name: /^change password$/i }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body.current_password).toBe('OldPass123');
    expect(body.new_password).toBe('NewPass123');
    await screen.findByText(/password changed/i);
  });

  it('rejects a mismatched confirmation without calling the API', async () => {
    stubPrefs();
    let called = false;
    server.use(
      http.post(CHANGE_URL, () => {
        called = true;
        return HttpResponse.json({ status: 'ok' });
      })
    );

    renderPage();
    await screen.findByPlaceholderText('Your name');

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText('Current password'), 'OldPass123');
    await user.type(screen.getByPlaceholderText('New password'), 'NewPass123');
    await user.type(screen.getByPlaceholderText('Confirm new password'), 'Different123');
    await user.click(screen.getByRole('button', { name: /^change password$/i }));

    await screen.findByText(/passwords do not match/i);
    expect(called).toBe(false);
  });

  it('surfaces the backend error detail when the current password is wrong', async () => {
    stubPrefs();
    server.use(
      http.post(CHANGE_URL, () =>
        HttpResponse.json({ detail: 'Current password is incorrect' }, { status: 400 })
      )
    );

    renderPage();
    await screen.findByPlaceholderText('Your name');

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText('Current password'), 'WrongPass1');
    await user.type(screen.getByPlaceholderText('New password'), 'NewPass123');
    await user.type(screen.getByPlaceholderText('Confirm new password'), 'NewPass123');
    await user.click(screen.getByRole('button', { name: /^change password$/i }));

    await screen.findByText(/current password is incorrect/i);
  });
});
