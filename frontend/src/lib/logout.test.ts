import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { createClient } from './apiClient';
import { authApi } from './auth';

// ISSUE-042 (H11) — there must be exactly one logout path, and it must revoke
// the refresh-token jti server-side. The legacy SDK shim `client.auth.logout()`
// POSTed no body (server never revoked the refresh jti → session resurrectable
// via /auth/refresh) and left `pos_refresh_token` in localStorage. It is removed
// in favour of the canonical `authApi.logout()` (used by DashboardLayout via
// useAuth().logout()).

const BASE = 'http://127.0.0.1:8000';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('logout (ISSUE-042)', () => {
  it('does not expose the divergent bodyless client.auth.logout shim [AC3]', () => {
    const client = createClient();
    // The whole SDK `auth` shim is gone (ISSUE-095) — so there is no
    // divergent `client.auth.logout` to drift from the canonical authApi.logout.
    expect((client as unknown as { auth?: unknown }).auth).toBeUndefined();
  });

  it('authApi.logout revokes via the cookie and clears both keys [AC1/AC2]', async () => {
    localStorage.setItem('pos_auth_token', 'access-jwt');
    // FE-01: an old build may have left a refresh token in localStorage; logout
    // must purge it. The token sent for revocation now rides the HttpOnly cookie.
    localStorage.setItem('pos_refresh_token', 'legacy-refresh-jwt');

    let postedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/auth/logout`, async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ success: true });
      })
    );

    await authApi.logout();

    // No body token — the server revokes the jti from the HttpOnly refresh cookie
    // (sent via withCredentials) and expires it; without revocation a subsequent
    // /auth/refresh would resurrect the session.
    expect(postedBody).toEqual({});
    // Both halves of the local session are cleared (incl. any legacy refresh copy).
    expect(localStorage.getItem('pos_auth_token')).toBeNull();
    expect(localStorage.getItem('pos_refresh_token')).toBeNull();
  });
});
