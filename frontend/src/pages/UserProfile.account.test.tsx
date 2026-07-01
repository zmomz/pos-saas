import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AccessibilityProvider } from '@/contexts/AccessibilityContext';
import UserProfile from './UserProfile';

// #203 (M1·Auth, parity #4) — the profile screen lets a user edit their own
// account name, email and phone, persisted through PUT /users/profile.

const BASE = 'http://127.0.0.1:8000/api/v1';

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
      HttpResponse.json({ id: 'u1', email: 'old@b.com', name: 'Old Name', phone: '', role: 'user' })
    )
  );
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile — account editing (#203)', () => {
  it('loads the account name/email/phone from the server on mount', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByLabelText(/^email$/i)).toHaveValue('old@b.com'));
    expect(screen.getByLabelText(/full name/i)).toHaveValue('Old Name');
    expect(screen.getByLabelText(/phone/i)).toHaveValue('');
  });

  it('persists edited name/email/phone via PUT /users/profile', async () => {
    let putBody: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/users/profile`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 'u1',
          email: 'new@b.com',
          name: 'New Name',
          phone: '+966500000000',
          role: 'user',
        });
      })
    );

    const user = userEvent.setup();
    renderPage();

    const emailInput = await screen.findByLabelText(/^email$/i);
    // Wait for the on-mount load to settle before editing, else it overwrites.
    await waitFor(() => expect(emailInput).toHaveValue('old@b.com'));
    await user.clear(emailInput);
    await user.type(emailInput, 'new@b.com');
    const phoneInput = screen.getByLabelText(/phone/i);
    await user.type(phoneInput, '+966500000000');

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody).toMatchObject({ email: 'new@b.com', phone: '+966500000000' });
  });

  it('rejects an invalid email before calling the server', async () => {
    let called = false;
    server.use(
      http.put(`${BASE}/users/profile`, () => {
        called = true;
        return HttpResponse.json({});
      })
    );

    const user = userEvent.setup();
    renderPage();

    const emailInput = await screen.findByLabelText(/^email$/i);
    await waitFor(() => expect(emailInput).toHaveValue('old@b.com'));
    await user.clear(emailInput);
    await user.type(emailInput, 'not-an-email');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await screen.findByText(/valid email/i);
    expect(called).toBe(false);
  });

  it('surfaces the server error when the email is already in use', async () => {
    server.use(
      http.put(`${BASE}/users/profile`, () =>
        HttpResponse.json({ detail: 'Email already in use' }, { status: 409 })
      )
    );

    const user = userEvent.setup();
    renderPage();

    const emailInput = await screen.findByLabelText(/^email$/i);
    await waitFor(() => expect(emailInput).toHaveValue('old@b.com'));
    await user.clear(emailInput);
    await user.type(emailInput, 'taken@b.com');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await screen.findByText(/already in use/i);
  });
});
