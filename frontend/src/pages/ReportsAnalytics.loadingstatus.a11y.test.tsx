import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-226 (a11y · SR pass) — while the reports page loaded, every panel showed
// a purely-visual `<Skeleton>` placeholder. Skeletons are decorative (no text,
// no role), so a screen-reader operator got total silence during the fetches
// with no cue that report data was in flight (WCAG 4.1.3 Status Messages). The
// page must expose a live `role="status"` region that announces the aggregate
// loading state and its completion.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ReportsAnalytics />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Keep every report panel loading by never resolving its fetch.
function stubPending() {
  server.use(http.get(`${BASE}/api/v1/*`, () => new Promise(() => {})));
}

// Settle every report fetch immediately. A 500 drives each fetcher into its
// catch branch (safe error state, no data dereference) while still clearing the
// loading flag in `finally` — which is all the aggregate status region tracks.
function stubResolved() {
  server.use(http.get(`${BASE}/api/v1/*`, () => new HttpResponse(null, { status: 500 })));
}

describe('ReportsAnalytics loading-state a11y (ISSUE-226)', () => {
  it('announces the report loading state through a role="status" live region', () => {
    stubPending();
    renderPage();

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent(/loading/i);
  });

  it('stops announcing loading once every report panel has resolved', async () => {
    stubResolved();
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('status')).not.toHaveTextContent(/loading/i);
    });
  });
});
