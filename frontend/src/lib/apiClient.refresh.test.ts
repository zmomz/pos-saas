import { describe, it, expect, beforeAll, afterAll, afterEach, vi, beforeEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { createClient, getToken } from './apiClient';

// ISSUE-041: the 401 interceptor must attempt exactly one silent refresh and
// replay the original request before clearing the session — so a user with a
// valid 7-day refresh token stays signed in past the 24h access-token boundary.
const BASE = 'http://127.0.0.1:8000';
const PROTECTED = `${BASE}/api/v1/entities/widgets`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;

const client = createClient();

const realLocation = window.location;
let assignMock: ReturnType<typeof vi.fn>;

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  // @ts-expect-error - restore the real jsdom location
  window.location = realLocation;
});

beforeEach(() => {
  localStorage.clear();
  // jsdom's location.assign isn't reconfigurable; swap in a plain stub so the
  // logout-redirect path is observable and pathname stays off /login.
  assignMock = vi.fn();
  // @ts-expect-error - replace the read-only jsdom location with a stub
  delete window.location;
  // @ts-expect-error - assign a minimal stub location
  window.location = { ...realLocation, pathname: '/', assign: assignMock };
});

describe('401 interceptor — silent refresh', () => {
  it('refreshes once and replays the original request when the access token is expired', async () => {
    localStorage.setItem('pos_auth_token', 'expired');
    localStorage.setItem('pos_refresh_token', 'good-refresh');

    let protectedCalls = 0;
    let refreshCalls = 0;
    server.use(
      http.get(PROTECTED, ({ request }) => {
        protectedCalls += 1;
        const auth = request.headers.get('authorization');
        if (auth === 'Bearer fresh') {
          return HttpResponse.json({ items: [{ id: 1 }], total: 1 });
        }
        return new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH, () => {
        refreshCalls += 1;
        return HttpResponse.json({ token: 'fresh' });
      })
    );

    const res = await client.entities.widgets.query<{ items: { id: number }[]; total: number }>();

    expect(refreshCalls).toBe(1);
    expect(protectedCalls).toBe(2); // initial 401 + replay
    expect(res.data.items[0].id).toBe(1);
    expect(getToken()).toBe('fresh');
  });

  it('logs out cleanly when the refresh token is rejected — no retry loop', async () => {
    localStorage.setItem('pos_auth_token', 'expired');
    localStorage.setItem('pos_refresh_token', 'stale-refresh');

    let protectedCalls = 0;
    let refreshCalls = 0;
    server.use(
      http.get(PROTECTED, () => {
        protectedCalls += 1;
        return new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH, () => {
        refreshCalls += 1;
        return new HttpResponse(null, { status: 401 });
      })
    );

    const expired = vi.fn();
    window.addEventListener('pos:session-expired', expired);

    await expect(client.entities.widgets.query()).rejects.toThrow();

    expect(refreshCalls).toBe(1); // exactly one refresh attempt
    expect(protectedCalls).toBe(1); // not replayed when refresh fails
    expect(getToken()).toBeNull(); // session cleared
    expect(expired).toHaveBeenCalledTimes(1);
    expect(assignMock).toHaveBeenCalledWith('/login');

    window.removeEventListener('pos:session-expired', expired);
  });

  it('refreshes at most once even if the replayed request still 401s', async () => {
    localStorage.setItem('pos_auth_token', 'expired');
    localStorage.setItem('pos_refresh_token', 'good-refresh');

    let protectedCalls = 0;
    let refreshCalls = 0;
    server.use(
      // Always 401, even with the fresh token — simulates a revoked grant.
      http.get(PROTECTED, () => {
        protectedCalls += 1;
        return new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH, () => {
        refreshCalls += 1;
        return HttpResponse.json({ token: 'fresh' });
      })
    );

    await expect(client.entities.widgets.query()).rejects.toThrow();

    expect(refreshCalls).toBe(1); // no second refresh on the replayed 401
    expect(protectedCalls).toBe(2); // original + one replay, then give up
    expect(getToken()).toBeNull();
    expect(assignMock).toHaveBeenCalledWith('/login');
  });
});
