import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('frontend observability (Sentry, config-gated)', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it('is a no-op (returns false) without VITE_SENTRY_DSN', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '');
    const { initSentry } = await import('./observability');
    expect(initSentry()).toBe(false);
  });

  it('initialises when a DSN is configured', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0');
    const { initSentry } = await import('./observability');
    expect(initSentry()).toBe(true);
  });
});
