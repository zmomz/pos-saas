import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y) — screen-reader pass on the KDS board controls. The two
// segmented controls at the top of the board — the Active/Completed *board
// view* toggle and the *station filter* tabs — were bare `.dxr-seg` <div>s.
// Each SegButton carries its own `aria-pressed`, but the group itself had no
// accessible name: a screen-reader cook hears "Active, pressed / Completed"
// and "All stations, pressed / Grill" with no cue as to WHAT those toggles
// switch. Each segmented control must be a labelled `group` landmark.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [
  { id: 1, name: 'Grill', name_ar: 'الشواية' },
  { id: 2, name: 'Cold', name_ar: 'البارد' },
];

function renderPage(stations: typeof STATIONS) {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(stations)),
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

describe('KDS segmented-control group a11y (ISSUE-226)', () => {
  it('exposes the board-view toggle as a labelled group', async () => {
    renderPage(STATIONS);
    const group = await screen.findByRole('group', { name: /board view/i });
    // The Active/Completed toggles live inside the labelled group.
    expect(group).toContainElement(screen.getByRole('button', { name: /active/i }));
    expect(group).toContainElement(screen.getByRole('button', { name: /completed/i }));
  });

  it('exposes the station-filter tabs as a labelled group', async () => {
    renderPage(STATIONS);
    const group = await screen.findByRole('group', { name: /station/i });
    expect(group).toContainElement(screen.getByRole('button', { name: /all stations/i }));
    expect(group).toContainElement(screen.getByRole('button', { name: /grill/i }));
  });
});
