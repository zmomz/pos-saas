import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MfaSettings from './MfaSettings';

// ISSUE-202 — two-step verification enrollment + status in the Security card.
const BASE = 'http://127.0.0.1:8000/api/v1';

function renderSettings() {
  return render(
    <LanguageProvider>
      <MfaSettings />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MfaSettings', () => {
  it('shows the On state with remaining recovery codes when enabled', async () => {
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: true, recovery_codes_remaining: 5 })
      )
    );
    renderSettings();
    expect(await screen.findByText('On')).toBeInTheDocument();
    expect(screen.getByText(/5 recovery codes left/i)).toBeInTheDocument();
    // No setup CTA when already enabled.
    expect(screen.queryByRole('button', { name: /^Set up$/i })).toBeNull();
  });

  it('walks enroll → activate and reveals recovery codes', async () => {
    let activateBody: any = null;
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: false, recovery_codes_remaining: 0 })
      ),
      http.post(`${BASE}/auth/mfa/enroll`, () =>
        HttpResponse.json({ secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://x', enabled: false })
      ),
      http.post(`${BASE}/auth/mfa/activate`, async ({ request }) => {
        activateBody = await request.json();
        return HttpResponse.json({ enabled: true, recovery_codes: ['aaaa-1111', 'bbbb-2222'] });
      })
    );

    const user = userEvent.setup();
    renderSettings();

    await user.click(await screen.findByRole('button', { name: /^Set up$/i }));

    // The shared secret is shown for manual entry.
    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();

    // Enter the code; onComplete activates.
    await user.type(screen.getByLabelText('Set up your authenticator'), '654321');

    await waitFor(() => expect(activateBody?.code).toBe('654321'));
    // Recovery codes are revealed once.
    expect(await screen.findByText('aaaa-1111')).toBeInTheDocument();
    expect(screen.getByText('bbbb-2222')).toBeInTheDocument();
  });

  it('surfaces an invalid-code error on a failed activation', async () => {
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: false, recovery_codes_remaining: 0 })
      ),
      http.post(`${BASE}/auth/mfa/enroll`, () =>
        HttpResponse.json({ secret: 'SECRET', otpauth_uri: 'otpauth://x', enabled: false })
      ),
      http.post(`${BASE}/auth/mfa/activate`, () =>
        HttpResponse.json({ detail: 'Invalid verification code.' }, { status: 400 })
      )
    );

    const user = userEvent.setup();
    renderSettings();

    await user.click(await screen.findByRole('button', { name: /^Set up$/i }));
    await screen.findByText('SECRET');
    await user.type(screen.getByLabelText('Set up your authenticator'), '000000');

    expect(await screen.findByText(/Invalid verification code/i)).toBeInTheDocument();
  });
});
