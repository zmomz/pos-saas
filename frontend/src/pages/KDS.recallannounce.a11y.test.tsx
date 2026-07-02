import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (SR pass) — recalling a bumped ticket brings its card back onto the
// active line, but that result was SILENT to a screen reader: a cook who tabs
// onto the Recall control and presses Enter got no confirmation the order
// returned (WCAG 4.1.3 status messages). The KDS polite live region now narrates
// each confirmed recall, mirroring the fired-order and bump announcers.

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

describe('KDS recall announcement (ISSUE-226, a11y SR pass)', () => {
  it('announces the order by reference after a confirmed recall', async () => {
    let recalled = false;
    server.use(
      http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
      http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () => {
        // The Completed board shows the bumped card until it is recalled.
        const items = recalled ? [] : [bumpedCard()];
        return HttpResponse.json({ items, total: items.length });
      }),
      http.post(`${BASE}/api/v1/restaurant/kds/9/recall`, () => {
        recalled = true;
        return HttpResponse.json({ ...bumpedCard(), status: 'active' });
      })
    );
    renderPage();

    // Switch to the Completed board so the bumped card (with its Recall control)
    // is visible.
    await userEvent.click(await screen.findByText(/completed/i));
    await screen.findByText('Burger');

    await userEvent.click(screen.getByRole('button', { name: /recall/i }));

    await waitFor(() => expect(recalled).toBe(true));
    const announcer = screen.getByTestId('kds-announcer');
    await waitFor(() => expect(announcer).toHaveTextContent(/Order recalled: Order #5/i));
  });
});
