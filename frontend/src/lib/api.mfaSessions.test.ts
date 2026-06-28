import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import {
  getMfaStatus,
  enrollMfa,
  activateMfa,
  getActiveSessions,
  revokeSession,
  revokeOtherSessions,
} from './api';

// ISSUE-202 — the MFA enroll/activate/status + active-session list/revoke client
// helpers hit the real /auth/mfa/* and /auth/sessions* endpoints.
const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MFA client helpers', () => {
  it('reads MFA status', async () => {
    server.use(
      http.get(`${BASE}/auth/mfa/status`, () =>
        HttpResponse.json({ enabled: true, recovery_codes_remaining: 4 })
      )
    );
    const status = await getMfaStatus();
    expect(status.enabled).toBe(true);
    expect(status.recovery_codes_remaining).toBe(4);
  });

  it('begins enrollment', async () => {
    server.use(
      http.post(`${BASE}/auth/mfa/enroll`, () =>
        HttpResponse.json({ secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://x', enabled: false })
      )
    );
    const enroll = await enrollMfa();
    expect(enroll.secret).toBe('JBSWY3DPEHPK3PXP');
    expect(enroll.otpauth_uri).toContain('otpauth://');
  });

  it('activates with a code and returns recovery codes', async () => {
    let body: any = null;
    server.use(
      http.post(`${BASE}/auth/mfa/activate`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ enabled: true, recovery_codes: ['aaaa-bbbb', 'cccc-dddd'] });
      })
    );
    const result = await activateMfa('123456');
    expect(body.code).toBe('123456');
    expect(result.recovery_codes).toHaveLength(2);
  });
});

describe('active-session client helpers', () => {
  it('unwraps the sessions array', async () => {
    server.use(
      http.get(`${BASE}/auth/sessions`, () =>
        HttpResponse.json({
          sessions: [
            { id: 's1', current: true, user_agent: 'UA', ip_address: '1.1.1.1', created_at: null, last_used_at: null },
            { id: 's2', current: false, user_agent: null, ip_address: null, created_at: null, last_used_at: null },
          ],
        })
      )
    );
    const sessions = await getActiveSessions();
    expect(sessions).toHaveLength(2);
    expect(sessions[0].current).toBe(true);
  });

  it('revokes a single session by id', async () => {
    let hit: string | null = null;
    server.use(
      http.delete(`${BASE}/auth/sessions/:id`, ({ params }) => {
        hit = params.id as string;
        return HttpResponse.json({ success: true, revoked: 1 });
      })
    );
    await revokeSession('abc');
    expect(hit).toBe('abc');
  });

  it('revokes all other sessions and returns the count', async () => {
    server.use(
      http.delete(`${BASE}/auth/sessions/others`, () =>
        HttpResponse.json({ success: true, revoked: 3 })
      )
    );
    const revoked = await revokeOtherSessions();
    expect(revoked).toBe(3);
  });
});
