import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y) — screen-reader pass on the KDS. The board-view and
// station-filter segmented controls previously marked the selected tab with a
// visual `data-active` attribute only, so a screen-reader cook could not tell
// which board / station filter was active. Each segment must now expose its
// selected state via `aria-pressed` (SegButton primitive).

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
    http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
  return render(
    <LanguageProvider>
      <KDS />
    </LanguageProvider>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('KDS segmented-control a11y (ISSUE-226)', () => {
  it('announces the active board-view tab via aria-pressed', async () => {
    renderPage();
    // "Active" board is selected by default; "Completed" is not.
    const active = await screen.findByRole('button', { name: /active/i });
    expect(active).toHaveAttribute('aria-pressed', 'true');
    const completed = screen.getByRole('button', { name: /completed/i });
    expect(completed).toHaveAttribute('aria-pressed', 'false');
  });

  it('announces the active station-filter tab via aria-pressed', async () => {
    renderPage();
    const allStations = await screen.findByRole('button', { name: /all stations/i });
    expect(allStations).toHaveAttribute('aria-pressed', 'true');
    const grill = screen.getByRole('button', { name: 'Grill' });
    expect(grill).toHaveAttribute('aria-pressed', 'false');
  });
});
