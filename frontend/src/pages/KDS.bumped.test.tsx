import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-073 — the KDS recall button was gated on status==='bumped' but the
// board only ever loaded active cards, so it never rendered. The kitchen now
// has a "Completed" view that lists recently-bumped cards and can recall one
// back to the active board.

const BASE = 'http://127.0.0.1:8000';

const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

function bumpedCard() {
  return {
    id: 9,
    order_ticket_id: 5,
    table_id: 3,
    station_id: 1,
    course: null,
    status: 'bumped',
    items: [{ item_id: 1, name: 'Burger', qty: 2, modifiers: [] }],
    fired_at: '2026-06-14T10:00:00',
    bumped_at: '2026-06-14T10:05:00',
  };
}

function renderPage() {
  return render(
    <LanguageProvider>
      <KDS />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('KDS bumped-card view (ISSUE-073)', () => {
  it('shows bumped cards when the Completed view is selected', async () => {
    server.use(
      http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
      http.get(`${BASE}/api/v1/restaurant/kds/tickets`, ({ request }) => {
        const status = new URL(request.url).searchParams.get('status');
        const items = status === 'bumped' ? [bumpedCard()] : [];
        return HttpResponse.json({ items, total: items.length });
      })
    );
    renderPage();

    // Default (active) board has nothing on it.
    await screen.findByText(/no .*tickets/i);
    expect(screen.queryByText('Burger')).not.toBeInTheDocument();

    // Switching to the Completed view fetches and lists bumped cards.
    await userEvent.click(screen.getByRole('button', { name: /completed/i }));
    expect(await screen.findByText('Burger')).toBeInTheDocument();
  });

  it('recalls a bumped card back to the active board', async () => {
    let recalled = false;
    server.use(
      http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
      http.get(`${BASE}/api/v1/restaurant/kds/tickets`, ({ request }) => {
        const status = new URL(request.url).searchParams.get('status');
        const items = status === 'bumped' && !recalled ? [bumpedCard()] : [];
        return HttpResponse.json({ items, total: items.length });
      }),
      http.post(`${BASE}/api/v1/restaurant/kds/9/recall`, () => {
        recalled = true;
        return HttpResponse.json({ ...bumpedCard(), status: 'active' });
      })
    );
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /completed/i }));
    await screen.findByText('Burger');

    // The recall control is now reachable on a bumped card.
    await userEvent.click(screen.getByRole('button', { name: /recall/i }));

    // After recall the card leaves the Completed board.
    await waitFor(() => expect(recalled).toBe(true));
    await waitFor(() => expect(screen.queryByText('Burger')).not.toBeInTheDocument());
  });
});
