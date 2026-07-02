import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (SR pass) — bumping a ticket optimistically removes its card from
// the active board, but that result was SILENT to a screen reader: a cook who
// tabs onto the Bump control and presses Enter got no confirmation the order
// left the line (WCAG 4.1.3 status messages). The KDS polite live region now
// narrates each confirmed bump, mirroring the fired-order announcer.

const BASE = 'http://127.0.0.1:8000';

const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

function activeCard() {
  return {
    id: 9,
    order_ticket_id: 5,
    table_id: 3,
    station_id: 1,
    course: null,
    status: 'active',
    items: [{ item_id: 1, name: 'Burger', qty: 2, modifiers: [] }],
    fired_at: '2026-06-14T10:00:00',
    bumped_at: null,
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

describe('KDS bump announcement (ISSUE-226, a11y SR pass)', () => {
  it('the announcer live region is silent on first paint', async () => {
    server.use(
      http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
      http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () =>
        HttpResponse.json({ items: [activeCard()], total: 1 })
      )
    );
    renderPage();

    // Wait for the board to paint the card, then assert nothing is announced yet.
    expect(await screen.findByText('Burger')).toBeInTheDocument();
    const announcer = screen.getByTestId('kds-announcer');
    expect(announcer).toHaveAttribute('aria-live', 'polite');
    expect(announcer).toHaveTextContent('');
  });

  it('announces the order by reference after a confirmed bump', async () => {
    let bumped = false;
    server.use(
      http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
      http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () => {
        const items = bumped ? [] : [activeCard()];
        return HttpResponse.json({ items, total: items.length });
      }),
      http.post(`${BASE}/api/v1/restaurant/kds/9/bump`, () => {
        bumped = true;
        return HttpResponse.json({ ...activeCard(), status: 'bumped' });
      })
    );
    renderPage();

    await screen.findByText('Burger');
    await userEvent.click(screen.getByRole('button', { name: /bump/i }));

    await waitFor(() => expect(bumped).toBe(true));
    const announcer = screen.getByTestId('kds-announcer');
    await waitFor(() => expect(announcer).toHaveTextContent(/Order bumped: Order #5/i));
  });
});
