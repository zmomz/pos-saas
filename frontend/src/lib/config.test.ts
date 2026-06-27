import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// FE-10: the runtime-config module used to emit debug `console.log` calls on
// every app load (e.g. "Config still loading, using default config"). Those
// must be gated so a production build is silent.
describe('config module debug logging is dev-gated', () => {
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

  it('still emits debug logging from getConfig in development', async () => {
    vi.stubEnv('DEV', true);
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const { getConfig } = await import('./config');

    getConfig();

    expect(spy).toHaveBeenCalled();
  });
});
