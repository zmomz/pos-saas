import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PackageManagement from './PackageManagement';

// ISSUE-226 (a11y · SR pass) — while the packages list loaded, the page painted
// a bespoke spinner ring next to visible "Loading…" text, but nothing marked it
// as a live status region: no `role="status"`/`aria-live`. A screen-reader
// operator got silence during the fetch with no cue that work was in flight
// (WCAG 4.1.3 Status Messages). The loading treatment must expose an accessible
// status role so assistive tech announces it — the shared `LoadingState` does.

const BASE = 'http://127.0.0.1:8000';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PackageManagement loading-state a11y (ISSUE-226)', () => {
  it('exposes the packages-list loading spinner as a role="status" live region', async () => {
    // Hold the list request open so the loading branch stays mounted.
    server.use(
      http.get(`${BASE}/api/v1/packages/list`, () => new Promise(() => {})),
    );

    render(
      <MemoryRouter>
        <LanguageProvider>
          <PackageManagement />
        </LanguageProvider>
      </MemoryRouter>,
    );

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/loading/i);
  });
});
