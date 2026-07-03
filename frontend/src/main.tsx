import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import App from './App.tsx';
import './index.css';
import { loadRuntimeConfig } from './lib/config.ts';
import { debugLog } from './lib/debug.ts';
import { initSentry, Sentry } from './lib/observability.ts';

// Error tracking (Phase 3): config-gated, no-op unless VITE_SENTRY_DSN is set.
initSentry();

// Load runtime configuration before rendering the app
async function initializeApp() {
  try {
    await loadRuntimeConfig();
    debugLog('Runtime configuration loaded successfully');
  } catch (error) {
    console.warn(
      'Failed to load runtime configuration, using defaults:',
      error
    );
  }

  // Render the app inside a Sentry error boundary so unhandled render errors are
  // reported (when Sentry is configured) and the user sees a graceful fallback.
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Sentry.ErrorBoundary
        fallback={
          <div style={{ padding: 24, textAlign: 'center' }}>
            Something went wrong. Please refresh the page.
          </div>
        }
      >
        <App />
      </Sentry.ErrorBoundary>
    </StrictMode>
  );

  // Offline POS (Phase E): register the app-shell service worker so the
  // terminal keeps loading without a network. Best-effort; only in production
  // builds and where service workers are available.
  if ('serviceWorker' in navigator && import.meta.env.PROD) {
    // ISSUE-2 (deploy hygiene): the new SW calls skipWaiting()+clients.claim(),
    // so on a fresh deploy it takes control of THIS already-open tab — but taking
    // control does not re-execute the old JS that is already running, and the new
    // SW's activate handler evicts the prior build's caches. A tab left on the old
    // bundle would then miss on any not-yet-loaded lazy chunk (old hash, evicted
    // from cache AND replaced on the server) and hard-fail. So when a NEW worker
    // takes over a tab that an OLD worker was already controlling, reload once to
    // swap the whole tab onto the new build atomically.
    //
    // `hadController` is true only for a returning client that a SW already
    // controlled at load; on the first-ever visit there is no controller and no
    // old bundle to swap, so the initial activation must NOT trigger a reload.
    const hadController = !!navigator.serviceWorker.controller;
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing || !hadController) return;
      refreshing = true;
      window.location.reload();
    });
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .catch((err) => console.warn('SW registration failed:', err));
    });
  }
}

// Initialize the app
initializeApp();
