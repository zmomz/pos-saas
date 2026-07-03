import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// FE-10 / prod-hygiene: the runtime-config module used to emit `🔧 DEBUG …`
// console.log calls on every app load. They ran through the dev-only debugLog
// (so prod never printed them), but the string literals still shipped in the
// bundle as no-op call arguments — so the logging was removed outright. getConfig
// must now be silent in every mode, dev included.
describe('config module emits no debug logging', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not console.log from getConfig in a production build', async () => {
    vi.stubEnv('DEV', false);
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const { getConfig } = await import('./config');

    getConfig();

    expect(spy).not.toHaveBeenCalled();
  });

  it('does not console.log from getConfig in development either', async () => {
    vi.stubEnv('DEV', true);
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const { getConfig } = await import('./config');

    getConfig();

    expect(spy).not.toHaveBeenCalled();
  });
});
