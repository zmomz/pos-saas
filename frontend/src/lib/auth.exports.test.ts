import { describe, it, expect } from 'vitest';
import * as authModule from './auth';
import { authApi } from './auth';

// ISSUE-096 — after #41 wired authApi.refreshAccessToken() into the 401
// interceptor, the refresh flow has exactly ONE live implementation. The old
// `getRefreshToken` helper was exported but consumed only inside auth.ts (and
// nowhere else in the app), so its public export was dead residue. The live
// refresh path must remain; no unused refresh-token helper may leak out.
describe('auth module public surface (ISSUE-096)', () => {
  it('keeps the live refreshAccessToken wired through authApi', () => {
    expect(typeof authApi.refreshAccessToken).toBe('function');
  });

  it('does not export a dead/unused refresh-token helper', () => {
    expect(Object.keys(authModule)).not.toContain('getRefreshToken');
  });
});
