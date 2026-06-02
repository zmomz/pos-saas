import * as Sentry from '@sentry/react';

/**
 * Frontend error tracking (Phase 3). No-op unless `VITE_SENTRY_DSN` is set, so
 * dev/CI run identically; production starts reporting the moment the DSN is
 * configured. Mirrors the backend's config-gated Sentry bootstrap.
 */
export function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment: (import.meta.env.MODE as string) || 'production',
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0),
    sendDefaultPii: false,
    integrations: [Sentry.browserTracingIntegration()],
  });
  return true;
}

export { Sentry };
