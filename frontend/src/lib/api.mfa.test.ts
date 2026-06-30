import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { getMfaStatus, enrollMfa, activateMfa, revokeSession } from './api';

// #202 (parity #1/#2) — thin client bindings over the ready backend MFA + session
// endpoints (/auth/mfa/* and /auth/sessions/*).

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MFA + session API bindings (#202)', () => {
  it('getMfaStatus reads /auth/mfa/status', async () => {
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: true, recovery_codes_remaining: 7 })
      )
    );

    expect(await getMfaStatus()).toEqual({ enabled: true, recovery_codes_remaining: 7 });
  });

  it('enrollMfa begins enrollment via /auth/mfa/enroll', async () => {
    server.use(
      http.post(`${BASE}/auth/mfa/enroll`, () =>
        HttpResponse.json({ secret: 'BASE32SECRET', otpauth_uri: 'otpauth://totp/x', enabled: false })
      )
    );

    const result = await enrollMfa();
    expect(result.secret).toBe('BASE32SECRET');
    expect(result.otpauth_uri).toBe('otpauth://totp/x');
  });

  it('activateMfa posts the code and returns recovery codes', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/auth/mfa/activate`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ enabled: true, recovery_codes: ['aaaa-bbbb', 'cccc-dddd'] });
      })
    );

    const result = await activateMfa('123456');
    expect(body).toEqual({ code: '123456' });
    expect(result.recovery_codes).toEqual(['aaaa-bbbb', 'cccc-dddd']);
  });

  it('revokeSession DELETEs the session by id', async () => {
    let hit = false;
    server.use(
      http.delete(`${BASE}/auth/sessions/sess-9`, () => {
        hit = true;
        return HttpResponse.json({ success: true, revoked: 1 });
      })
    );

    const result = await revokeSession('sess-9');
    expect(hit).toBe(true);
    expect(result.success).toBe(true);
  });
});
