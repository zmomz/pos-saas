import { describe, it, expect, beforeAll, beforeEach, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y · screen-reader pass) — the KDS board updates live over SSE:
// when a new ticket *fires*, a fresh card silently appears on the board. A cook
// using a screen reader gets no signal that a new order arrived. The live line
// must announce a newly-fired order through a polite live region, the same way
// the POS cart announces additions and the SPA announces route changes.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

function existingCard() {
  return {
    id: 1,
    order_ticket_id: 5,
    table_id: 3,
    station_id: 1,
    course: null,
    status: 'active',
    items: [{ item_id: 1, name: 'Burger', qty: 2, modifiers: [] }],
    fired_at: new Date().toISOString(),
  };
}

// The card that arrives over the wire as a `fired` event after the board loads.
function firedCard() {
  return {
    id: 2,
    order_ticket_id: 9,
    table_id: 4,
    station_id: 1,
    course: null,
    status: 'active',
    items: [{ item_id: 2, name: 'Fries', qty: 1, modifiers: [] }],
    fired_at: new Date().toISOString(),
  };
}

// A minimal, drivable EventSource stand-in. jsdom ships no EventSource, so the
// component's SSE path is normally skipped in tests; installing this lets a test
// open the stream and emit a `fired` frame exactly as the server would.
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onerror: ((e: unknown) => void) | null = null;
  private listeners: Record<string, ((e: { data: string }) => void)[]> = {};
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: (e: { data: string }) => void) {
    (this.listeners[type] ||= []).push(cb);
  }
  removeEventListener() {}
  close() {}
  emit(type: string, data: unknown) {
    (this.listeners[type] || []).forEach((cb) => cb({ data: JSON.stringify(data) }));
  }
}

function renderPage() {
  return render(
    <LanguageProvider>
      <KDS />
    </LanguageProvider>
  );
}

function serveBoard(cards: unknown[]) {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
    http.get(`${BASE}/api/v1/restaurant/kds/tickets`, ({ request }) => {
      const status = new URL(request.url).searchParams.get('status');
      const items = status === 'bumped' ? [] : cards;
      return HttpResponse.json({ items, total: items.length });
    }),
    http.post(`${BASE}/api/v1/restaurant/kds/stream-ticket`, () =>
      HttpResponse.json({ ticket: 'test-ticket' })
    )
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
// The SSE path only mints a stream ticket for an authenticated session.
beforeEach(() => localStorage.setItem('pos_auth_token', 'test-token'));
afterEach(() => {
  server.resetHandlers();
  MockEventSource.instances = [];
});
afterAll(() => server.close());

describe('KDS fired-order screen-reader announcement (ISSUE-226)', () => {
  it('announces a newly-fired order in a polite live region', async () => {
    vi.stubGlobal('EventSource', MockEventSource);
    try {
      serveBoard([existingCard()]);
      renderPage();

      // Board loads with the existing card and the stream opens.
      await screen.findByText('Burger');
      await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
      const es = MockEventSource.instances[0];

      // A polite live region exists but is silent about the pre-loaded board.
      const region = screen.getByTestId('kds-announcer');
      expect(region).toHaveAttribute('aria-live', 'polite');
      expect(region).toHaveTextContent('');

      // A new order fires over the stream.
      act(() => es.emit('fired', { card: firedCard() }));

      // The new card lands on the board *and* the order is announced.
      await screen.findByText('Fries');
      await waitFor(() => expect(region).toHaveTextContent(/order.*9/i));
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
