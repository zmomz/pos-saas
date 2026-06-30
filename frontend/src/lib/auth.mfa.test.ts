import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { authApi, isMfaChallenge, type AuthUser } from './auth';

// #202 (parity #1) — an MFA-enabled account does NOT get tokens from
// /auth/login; it gets a short-lived challenge ticket that must be exchanged
// (with a TOTP/recovery code) at /auth/login/mfa. The old login() blindly read
// response.data.token and would have stored `undefined` and dropped the user
// into a half-authenticated state. login() now discriminates the two shapes.

const BASE = 'http://127.0.0.1:8000';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
beforeEach(() => localStorage.clear());
afterAll(() => server.close());

describe('MFA login challenge (#202)', () => {
  it('returns an MFA challenge (and stores no token) when a second factor is required', async () => {
    server.use(
      http.post(`${BASE}/api/v1/auth/login`, () =>
        HttpResponse.json({ mfa_required: true, mfa_token: 'ticket-123' })
      )
    );

    const result = await authApi.login('a@b.com', 'pw');

    expect(isMfaChallenge(result)).toBe(true);
    if (isMfaChallenge(result)) expect(result.mfaToken).toBe('ticket-123');
    // No half-authenticated state: the access token is only minted after the
    // second factor is verified.
    expect(localStorage.getItem('pos_auth_token')).toBeNull();
  });

  it('returns the user and stores the token on a normal (no-MFA) password login', async () => {
    server.use(
      http.post(`${BASE}/api/v1/auth/login`, () =>
        HttpResponse.json({
          token: 'jwt',
          token_type: 'bearer',
          expires_at: 1,
          user: { id: '1', email: 'a@b.com', role: 'client' },
        })
      )
    );

    const result = await authApi.login('a@b.com', 'pw');

    expect(isMfaChallenge(result)).toBe(false);
    expect((result as AuthUser).email).toBe('a@b.com');
    expect(localStorage.getItem('pos_auth_token')).toBe('jwt');
  });

  it('completeMfaLogin exchanges the ticket + code for tokens and returns the user', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/auth/login/mfa`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          token: 'jwt2',
          token_type: 'bearer',
          expires_at: 1,
          user: { id: '1', email: 'a@b.com', role: 'client' },
        });
      })
    );

    const user = await authApi.completeMfaLogin('ticket-123', '123456');

    expect(body).toEqual({ mfa_token: 'ticket-123', code: '123456' });
    expect(user.email).toBe('a@b.com');
    expect(localStorage.getItem('pos_auth_token')).toBe('jwt2');
  });

  it('completeMfaLogin surfaces the server detail on a bad code', async () => {
    server.use(
      http.post(`${BASE}/api/v1/auth/login/mfa`, () =>
        HttpResponse.json({ detail: 'Invalid verification code' }, { status: 401 })
      )
    );

    await expect(authApi.completeMfaLogin('ticket-123', '000000')).rejects.toThrow(
      'Invalid verification code'
    );
  });
});
