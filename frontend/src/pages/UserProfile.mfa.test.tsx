import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import UserProfile from './UserProfile';

// #202 (parity #1/#2) — the profile is where a user enrolls in MFA and manages
// their active sessions (list + revoke).

const BASE = 'http://127.0.0.1:8000/api/v1';
const CHROME_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36';
const FIREFOX_UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0';

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
beforeEach(() => {
  localStorage.setItem('pos-language', 'en');
  server.use(
    http.get(`${BASE}/users/preferences`, () =>
      HttpResponse.json({ display_name: '', notification_prefs: {} })
    ),
    http.get(`${BASE}/auth/mfa/status`, () =>
      HttpResponse.json({ enabled: false, recovery_codes_remaining: 0 })
    ),
    http.get(`${BASE}/auth/sessions`, () => HttpResponse.json({ sessions: [] })),
    http.get(`${BASE}/users/profile`, () =>
      HttpResponse.json({ id: 'u1', email: 'me@b.com', name: 'Me', phone: '', role: 'user' })
    )
  );
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile — MFA enrollment (#202)', () => {
  it('enrolls in MFA: shows the secret, accepts a code, reveals recovery codes', async () => {
    server.use(
      http.post(`${BASE}/auth/mfa/enroll`, () =>
        HttpResponse.json({ secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/x', enabled: false })
      ),
      http.post(`${BASE}/auth/mfa/activate`, () =>
        HttpResponse.json({ enabled: true, recovery_codes: ['aaaa-bbbb', 'cccc-dddd'] })
      )
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /Enable two-factor/i }));

    // Secret is surfaced so the user can load it into an authenticator app.
    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Verification code'), '123456');
    await user.click(screen.getByRole('button', { name: /^Activate$/i }));

    // Recovery codes are shown once on activation.
    expect(await screen.findByText('aaaa-bbbb')).toBeInTheDocument();
    expect(screen.getByText('cccc-dddd')).toBeInTheDocument();
  });

  it('shows an enabled state with remaining recovery-code count when MFA is already on', async () => {
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: true, recovery_codes_remaining: 5 })
      )
    );
    renderPage();

    expect(await screen.findByText(/two-factor authentication is on/i)).toBeInTheDocument();
    expect(screen.getByText(/5/)).toBeInTheDocument();
  });
});

describe('UserProfile — session management (#202)', () => {
  it('lists active sessions and revokes a non-current one', async () => {
    let listCalls = 0;
    server.use(
      http.get(`${BASE}/auth/sessions`, () => {
        listCalls += 1;
        const sessions = [
          { id: 'sess-current', current: true, user_agent: CHROME_UA, created_at: '2026-06-01T10:00:00Z' },
          { id: 'sess-other', current: false, user_agent: FIREFOX_UA, created_at: '2026-06-02T10:00:00Z' },
        ];
        // After the revoke, the other session is gone.
        return HttpResponse.json({ sessions: listCalls === 1 ? sessions : sessions.slice(0, 1) });
      }),
      http.delete(`${BASE}/auth/sessions/sess-other`, () =>
        HttpResponse.json({ success: true, revoked: 1 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    // Both the current (Chrome) and the other (Firefox) session are listed.
    expect(await screen.findByText('Firefox')).toBeInTheDocument();
    expect(screen.getByText('Chrome')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Revoke/i }));

    // The revoked session disappears after the list refreshes.
    await waitFor(() => expect(screen.queryByText('Firefox')).not.toBeInTheDocument());
    expect(screen.getByText('Chrome')).toBeInTheDocument();
  });
});
