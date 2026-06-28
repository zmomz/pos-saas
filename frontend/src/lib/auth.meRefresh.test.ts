import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { authApi } from './auth';
import { getToken, setToken } from './apiClient';

// ISSUE-192 — a fresh page load with an expired access token but a still-valid
// refresh cookie must NOT log the user out. getCurrentUser drives the bootstrap
// (`AuthContext.checkAuthStatus`) and runs on the credential-less `authApi`
// client, so it has no response interceptor and previously cleared the session
// on the first /auth/me 401 — the one path FE-01's refresh cookie should rescue.
// getCurrentUser now attempts a single cookie-driven refresh and replays /auth/me
// before giving up.
const BASE = 'http://127.0.0.1:8000';
const ME = `${BASE}/api/v1/auth/me`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => localStorage.clear());

describe('ISSUE-192 — getCurrentUser refreshes before logging out', () => {
  it('expired access token + valid refresh cookie: refreshes and keeps the user signed in', async () => {
    setToken('expired'); // a session exists; the refresh token rides the cookie
    let refreshCalls = 0;
    server.use(
      http.get(ME, ({ request }) => {
        const auth = request.headers.get('authorization');
        // The expired token is rejected; the freshly-minted one is accepted.
        if (auth === 'Bearer access-2') {
          return HttpResponse.json({ id: '1', email: 'a@b.c', role: 'agent' });
        }
        return new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH, () => {
        refreshCalls += 1;
        return HttpResponse.json({ token: 'access-2' });
      })
    );

    const user = await authApi.getCurrentUser();

    expect(user?.email).toBe('a@b.c');
    expect(getToken()).toBe('access-2');
    expect(refreshCalls).toBe(1);
  });

  it('expired access token + dead refresh cookie: clears the session and returns null', async () => {
    setToken('expired');
    server.use(
      http.get(ME, () => new HttpResponse(null, { status: 401 })),
      http.post(REFRESH, () => new HttpResponse(null, { status: 401 }))
    );

    const user = await authApi.getCurrentUser();

    expect(user).toBeNull();
    expect(getToken()).toBeNull();
  });

  it('no session: returns null without hitting the network', async () => {
    // onUnhandledRequest:'error' would throw on any /auth/me or /auth/refresh call.
    const user = await authApi.getCurrentUser();
    expect(user).toBeNull();
  });
});
