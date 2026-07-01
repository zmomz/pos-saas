import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The report period selector (Daily/Weekly/Monthly) signalled
// its selected segment with `data-active` (styling) ALONE — no `aria-pressed`, so
// a screen-reader user got no cue which period was active (WCAG 1.4.1 / 4.1.2).

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ReportsAnalytics />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ReportsAnalytics period segmented-control a11y (#226)', () => {
  it('announces the active Daily/Weekly/Monthly period via aria-pressed', async () => {
    server.use(http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null)));
    renderPage();

    // 'daily' is the default period, so it must announce as pressed.
    expect(
      await screen.findByRole('button', { name: 'Daily', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Weekly', pressed: false })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Monthly', pressed: false })
    ).toBeInTheDocument();
  });
});
