import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentLandingPage from './AgentLandingPage';

// ISSUE-226 (a11y · SR pass) — while the public distributor brochure fetched its
// agent profile, the page painted a bespoke spinner ring next to visible
// "Loading…" text, but nothing marked it as a live status region: no
// `role="status"`/`aria-live`. A screen-reader prospect got silence during the
// fetch with no cue that work was in flight (WCAG 4.1.3 Status Messages). The
// loading treatment must expose an accessible status role so assistive tech
// announces it — the shared `LoadingState` does.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/p/7']}>
      <LanguageProvider>
        <Routes>
          <Route path="/p/:agentId" element={<AgentLandingPage />} />
        </Routes>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentLandingPage loading-state a11y (ISSUE-226)', () => {
  it('exposes the profile-fetch loading spinner as a role="status" live region', async () => {
    // Hold the profile request open so the loading branch stays mounted.
    server.use(http.get(`${BASE}/api/v1/tenant/agent/7/public`, () => new Promise(() => {})));

    renderPage();

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/loading/i);
  });
});
