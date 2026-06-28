import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AuthProvider } from '@/contexts/AuthContext';
import UserProfile from './UserProfile';

// ISSUE-078 — per-user profile + notification preferences are persisted
// server-side (no longer localStorage-only), so they follow the user across
// devices. The page loads them from the API on mount and PUTs them on save.
// #203 — the account identity (name/email/phone) loads/saves via /users/profile.

const BASE = 'http://127.0.0.1:8000/api/v1';
const PREFS_URL = `${BASE}/users/preferences`;
const PROFILE_URL = `${BASE}/users/profile`;

// The account tile fetches /users/profile on mount; every test needs it stubbed.
function stubProfile(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get(PROFILE_URL, () =>
      HttpResponse.json({
        id: 'u1',
        email: 'owner@shop.test',
        name: 'Owner',
        phone: null,
        role: 'client',
        ...overrides,
      })
    )
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LanguageProvider>
          <ThemeProvider>
            <UserProfile />
          </ThemeProvider>
        </LanguageProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UserProfile server persistence', () => {
  it('loads the persisted profile from the server on mount', async () => {
    stubProfile();
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
    stubProfile();
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

// #203 — account identity editing (name / email / phone) via /users/profile.
function stubPrefs() {
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
    )
  );
}

describe('UserProfile account editing (#203)', () => {
  it('loads name/email/phone from /users/profile on mount', async () => {
    stubPrefs();
    stubProfile({ name: 'Sara', email: 'sara@shop.test', phone: '+966500000000' });
    renderPage();

    expect(await screen.findByDisplayValue('Sara')).toBeInTheDocument();
    expect(screen.getByDisplayValue('sara@shop.test')).toBeInTheDocument();
    expect(screen.getByDisplayValue('+966500000000')).toBeInTheDocument();
  });

  it('persists name/email/phone via PUT /users/profile', async () => {
    stubPrefs();
    stubProfile({ name: 'Sara', email: 'sara@shop.test', phone: '' });
    let putBody: any = null;
    server.use(
      http.put(PROFILE_URL, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({
          id: 'u1',
          role: 'client',
          name: putBody.name,
          email: putBody.email,
          phone: putBody.phone,
        });
      })
    );

    renderPage();
    const phoneInput = await screen.findByPlaceholderText('Phone number');

    const user = userEvent.setup();
    await user.type(phoneInput, '+966512345678');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody.email).toBe('sara@shop.test');
    expect(putBody.phone).toBe('+966512345678');
    await screen.findByText(/profile updated/i);
  });

  it('blocks save and shows a validation message for an invalid email', async () => {
    stubPrefs();
    stubProfile({ email: 'sara@shop.test' });
    let called = false;
    server.use(
      http.put(PROFILE_URL, () => {
        called = true;
        return HttpResponse.json({});
      })
    );

    renderPage();
    const emailInput = await screen.findByDisplayValue('sara@shop.test');

    const user = userEvent.setup();
    await user.clear(emailInput);
    await user.type(emailInput, 'not-an-email');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await screen.findByText(/valid email address/i);
    expect(called).toBe(false);
  });

  it('surfaces a 409 email-in-use conflict honestly', async () => {
    stubPrefs();
    stubProfile({ email: 'sara@shop.test' });
    server.use(
      http.put(PROFILE_URL, () =>
        HttpResponse.json({ detail: 'That email is already in use' }, { status: 409 })
      )
    );

    renderPage();
    const emailInput = await screen.findByDisplayValue('sara@shop.test');

    const user = userEvent.setup();
    await user.clear(emailInput);
    await user.type(emailInput, 'taken@shop.test');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await screen.findByText(/already in use/i);
  });
});
