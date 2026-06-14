import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { createClient } from './atomsClient';
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
    expect(
      (client.auth as unknown as { logout?: unknown }).logout
    ).toBeUndefined();
  });

  it('authApi.logout revokes the refresh token and clears both keys [AC1/AC2]', async () => {
    localStorage.setItem('pos_auth_token', 'access-jwt');
    localStorage.setItem('pos_refresh_token', 'refresh-jwt');

    let postedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/auth/logout`, async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ success: true });
      })
    );

    await authApi.logout();

    // The refresh token is sent so the server revokes its jti — without this a
    // subsequent /auth/refresh would resurrect the session.
    expect(postedBody).toEqual({ refresh_token: 'refresh-jwt' });
    // Both halves of the local session are cleared.
    expect(localStorage.getItem('pos_auth_token')).toBeNull();
    expect(localStorage.getItem('pos_refresh_token')).toBeNull();
  });
});
