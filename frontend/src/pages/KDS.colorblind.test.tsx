import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y) — color-blind-safe KDS states. The "late" ticket state was
// signalled by COLOR ALONE (red border/tint + red timer text), which a
// red/green color-blind cook cannot distinguish from an on-time card. A late
// card must now also carry a NON-COLOR cue: a text label + warning icon.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

// A card fired well over the ten-minute "late" threshold, whatever the wall clock.
function lateCard() {
  return {
    id: 1,
    order_ticket_id: 5,
    table_id: 3,
    station_id: 1,
    course: null,
    status: 'active',
    items: [{ item_id: 1, name: 'Burger', qty: 2, modifiers: [] }],
    fired_at: '2020-01-01T00:00:00Z',
  };
}

// A card fired essentially now — not late.
function freshCard() {
  return {
    ...lateCard(),
    id: 2,
    order_ticket_id: 6,
    items: [{ item_id: 2, name: 'Fries', qty: 1, modifiers: [] }],
    fired_at: new Date().toISOString(),
  };
}

function renderPage() {
  return render(
    <LanguageProvider>
      <KDS />
    </LanguageProvider>
  );
}

function serveCards(cards: unknown[]) {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
    http.get(`${BASE}/api/v1/restaurant/kds/tickets`, ({ request }) => {
      const status = new URL(request.url).searchParams.get('status');
      const items = status === 'bumped' ? [] : cards;
      return HttpResponse.json({ items, total: items.length });
    })
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('KDS color-blind-safe late state (ISSUE-226)', () => {
  it('shows a non-color "Late" label on a late card', async () => {
    serveCards([lateCard()]);
    renderPage();

    await screen.findByText('Burger');
    // The state is conveyed as text, not just red styling.
    expect(screen.getByText(/late/i)).toBeInTheDocument();
  });

  it('does not show the Late label on an on-time card', async () => {
    serveCards([freshCard()]);
    renderPage();

    await screen.findByText('Fries');
    expect(screen.queryByText(/late/i)).not.toBeInTheDocument();
  });
});
