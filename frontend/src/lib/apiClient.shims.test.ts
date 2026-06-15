import { describe, it, expect } from 'vitest';
import { createClient } from './apiClient';

// ISSUE-095 — `atomsClient.ts` (migration cruft from the @metagptx/web-sdk
// drop-in) is renamed to `apiClient.ts`, and the unused SDK-shim auth surface
// (`auth.me` / `auth.login` / `auth.toLogin`) is removed: nothing in the app
// ever called it. Auth now flows through `authApi` in lib/auth.ts. The client
// keeps only the surface the app actually uses: `apiCall.invoke` + `entities`.

describe('apiClient (ISSUE-095)', () => {
  it('exposes the live client surface the app uses', () => {
    const client = createClient();
    expect(typeof client.apiCall.invoke).toBe('function');
    expect(client.entities).toBeDefined();
  });

  it('drops the unused SDK auth shims (me/login/toLogin)', () => {
    const client = createClient();
    expect((client as unknown as { auth?: unknown }).auth).toBeUndefined();
  });
});
