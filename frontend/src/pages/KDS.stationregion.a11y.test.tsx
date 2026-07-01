import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y) — screen-reader pass on the KDS board layout. Each prep-
// station column carried its name in a plain <h3> and its outstanding-ticket
// count in a bare number Badge, with no programmatic grouping. A screen-reader
// cook could neither navigate to a station nor perceive its workload without
// sighted reading of the heading + badge. Each column must now be a labelled
// landmark region whose accessible name names the station AND its ticket count.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [
  { id: 1, name: 'Grill', name_ar: 'الشواية' },
  { id: 2, name: 'Cold', name_ar: 'البارد' },
];

function ticket(id: number, station_id: number) {
  return {
    id,
    order_ticket_id: 100 + id,
    table_id: null,
    station_id,
    course: null,
    status: 'active',
    items: [{ item_id: id, name: 'Burger', qty: 1, modifiers: [] }],
    fired_at: '2026-07-01T12:00:00Z',
    bumped_at: null,
  };
}

function renderPage(tickets: ReturnType<typeof ticket>[]) {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
    http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () =>
      HttpResponse.json({ items: tickets, total: tickets.length }),
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

describe('KDS station-column region a11y (ISSUE-226)', () => {
  it('exposes each station column as a landmark region named by station + ticket count', async () => {
    renderPage([ticket(1, 1), ticket(2, 1)]);
    // Grill holds two tickets; its region name must convey both.
    const grill = await screen.findByRole('region', { name: /grill/i });
    expect(grill).toHaveAccessibleName(/grill/i);
    expect(grill).toHaveAccessibleName(/2 ticket/i);
  });

  it('reflects an empty station as zero tickets in its region name', async () => {
    renderPage([ticket(1, 1)]);
    const cold = await screen.findByRole('region', { name: /cold/i });
    expect(cold).toHaveAccessibleName(/0 ticket/i);
  });
});
