import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// FE-10: debug logging must be dev-only so it never ships to end users' consoles
// in a production build. `debugLog` is the single sanctioned chokepoint that all
// debug/diagnostic logging routes through; it forwards to console.log only when
// `import.meta.env.DEV` is true.
describe('debugLog (dev-only debug logging)', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('forwards its arguments to console.log in development', async () => {
    vi.stubEnv('DEV', true);
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const { debugLog } = await import('./debug');

    debugLog('hello', 42);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith('hello', 42);
  });

  it('does not call console.log in a production build', async () => {
    vi.stubEnv('DEV', false);
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const { debugLog } = await import('./debug');

    debugLog('should be silent');

    expect(spy).not.toHaveBeenCalled();
  });
});
