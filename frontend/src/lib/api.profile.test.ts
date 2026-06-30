import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { getUserProfile, updateUserProfile } from './api';

// #203 (M1·Auth, parity #4) — thin client bindings over the account profile
// endpoint (/users/profile) for self-service name/email/phone editing.

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('account profile API bindings (#203)', () => {
  it('getUserProfile reads name/email/phone from /users/profile', async () => {
    server.use(
      http.get(`${BASE}/users/profile`, () =>
        HttpResponse.json({
          id: 'u1',
          email: 'a@b.com',
          name: 'Jane',
          phone: '+966500000000',
          role: 'user',
        })
      )
    );

    const profile = await getUserProfile();
    expect(profile.email).toBe('a@b.com');
    expect(profile.name).toBe('Jane');
    expect(profile.phone).toBe('+966500000000');
  });

  it('updateUserProfile PUTs the edited fields and returns the saved profile', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/users/profile`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 'u1',
          email: 'new@b.com',
          name: 'Jane Doe',
          phone: '+966511111111',
          role: 'user',
        });
      })
    );

    const saved = await updateUserProfile({
      name: 'Jane Doe',
      email: 'new@b.com',
      phone: '+966511111111',
    });

    expect(body).toEqual({ name: 'Jane Doe', email: 'new@b.com', phone: '+966511111111' });
    expect(saved.email).toBe('new@b.com');
    expect(saved.phone).toBe('+966511111111');
  });
});
