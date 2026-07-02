import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y) — screen-reader pass on the KDS header. The "all-day"
// summary badge showed a ChefHat glyph followed by a bare number (the total
// outstanding fired-item quantity). A screen reader announced only the number
// with no context — the ChefHat carried the "all-day items" meaning visually
// and was invisible to assistive tech (WCAG 1.3.1 / 4.1.2). The badge must
// expose an accessible name that names WHAT the number counts.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

function ticket(id: number, station_id: number, qty: number) {
  return {
    id,
    order_ticket_id: 100 + id,
    table_id: null,
    station_id,
    course: null,
    status: 'active',
    items: [{ item_id: id, name: 'Burger', qty, modifiers: [] }],
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

describe('KDS all-day count a11y (ISSUE-226)', () => {
  it('gives the all-day summary badge an accessible name that names the count', async () => {
    // Two tickets carrying 2 + 3 = 5 outstanding items.
    renderPage([ticket(1, 1, 2), ticket(2, 1, 3)]);
    const badge = await screen.findByLabelText(/all.?day/i);
    expect(badge).toHaveAccessibleName(/all.?day/i);
    expect(badge).toHaveAccessibleName(/5/);
  });
});
