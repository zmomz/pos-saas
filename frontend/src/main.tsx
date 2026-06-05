import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import App from './App.tsx';
import './index.css';
import { loadRuntimeConfig } from './lib/config.ts';
import { initSentry, Sentry } from './lib/observability.ts';

// Error tracking (Phase 3): config-gated, no-op unless VITE_SENTRY_DSN is set.
initSentry();

// Load runtime configuration before rendering the app
async function initializeApp() {
  try {
    await loadRuntimeConfig();
    console.log('Runtime configuration loaded successfully');
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
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .catch((err) => console.warn('SW registration failed:', err));
    });
  }
}

// Initialize the app
initializeApp();
