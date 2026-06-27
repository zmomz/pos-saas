import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { authApi } from './auth';
import { getToken, setToken } from './apiClient';

// FE-01 (iteration 2 of 2) — move the refresh token out of localStorage.
// Iteration 1 made every token-minting endpoint also set the refresh token as an
// HttpOnly / SameSite cookie scoped to /api/v1/auth, and made /refresh + /logout
// accept it from that cookie. This iteration stops the SPA from persisting the
// refresh token in JS-reachable storage: login/register no longer write it,
// /refresh is driven by the cookie (empty body, withCredentials), and logout
// relies on the cookie + purges any legacy localStorage copy.
const BASE = 'http://127.0.0.1:8000';
const LOGIN = `${BASE}/api/v1/auth/login`;
const REGISTER = `${BASE}/api/v1/auth/register`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const LOGOUT = `${BASE}/api/v1/auth/logout`;
const REFRESH_KEY = 'pos_refresh_token';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => localStorage.clear());

describe('FE-01 — refresh token lives only in the HttpOnly cookie', () => {
  it('login keeps the access token but never persists the refresh token', async () => {
    server.use(
      http.post(LOGIN, () =>
        HttpResponse.json({
          token: 'access-1',
          token_type: 'bearer',
          expires_at: 0,
          refresh_token: 'must-not-be-stored',
          user: { id: '1', email: 'a@b.c', role: 'agent' },
        })
      )
    );

    const user = await authApi.login('a@b.c', 'pw');

    expect(user.email).toBe('a@b.c');
    expect(getToken()).toBe('access-1');
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('register never persists the refresh token either', async () => {
    server.use(
      http.post(REGISTER, () =>
        HttpResponse.json({
          token: 'access-1',
          token_type: 'bearer',
          expires_at: 0,
          refresh_token: 'must-not-be-stored',
          user: { id: '1', email: 'a@b.c', role: 'agent' },
        })
      )
    );

    await authApi.register('a@b.c', 'pw', 'Ann');

    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('refreshAccessToken refreshes from the cookie — empty body, with credentials', async () => {
    setToken('expired'); // a session exists; the refresh token rides the cookie
    let body: unknown = 'unset';
    let credentials: RequestCredentials | undefined;
    server.use(
      http.post(REFRESH, async ({ request }) => {
        credentials = request.credentials;
        body = await request.json().catch(() => null);
        return HttpResponse.json({ token: 'access-2' });
      })
    );

    const ok = await authApi.refreshAccessToken();

    expect(ok).toBe(true);
    expect(getToken()).toBe('access-2');
    // The refresh token is NOT sent in the body — the server reads the cookie.
    expect(body).not.toHaveProperty('refresh_token');
    // Cookie can only round-trip when the request is credentialed.
    expect(credentials).toBe('include');
  });

  it('refreshAccessToken makes no request and returns false when there is no session', async () => {
    // No access token set; onUnhandledRequest:'error' would throw on any network call.
    const ok = await authApi.refreshAccessToken();
    expect(ok).toBe(false);
  });

  it('logout relies on the cookie (no body token) and purges any legacy localStorage copy', async () => {
    setToken('access-1');
    localStorage.setItem(REFRESH_KEY, 'legacy-from-an-old-build');
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(LOGOUT, async ({ request }) => {
        body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
        return HttpResponse.json({ success: true });
      })
    );

    await authApi.logout();

    expect(body).toEqual({});
    expect(getToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});
