import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BrandingEditor from './BrandingEditor';

// ISSUE-226 (a11y · SR pass) — while the branding editor loaded, the page
// painted a bespoke spinner ring next to visible "Loading…" text, but nothing
// marked it as a live status region: no `role="status"`/`aria-live`. A
// screen-reader operator got silence during the fetch with no cue that work was
// in flight (WCAG 4.1.3 Status Messages). The loading treatment must expose an
// accessible status role so assistive tech announces it — the shared
// `LoadingState` does. This retires the last bespoke spinner flagged in the
// design audit.

const URL = 'http://127.0.0.1:8000/api/v1/tenant/agent/branding';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BrandingEditor loading-state a11y (ISSUE-226)', () => {
  it('exposes the branding-fetch loading spinner as a role="status" live region', async () => {
    // Hold the branding request open so the loading branch stays mounted.
    server.use(http.get(URL, () => new Promise(() => {})));

    render(
      <MemoryRouter>
        <LanguageProvider>
          <BrandingEditor />
        </LanguageProvider>
      </MemoryRouter>,
    );

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/loading/i);
  });
});
