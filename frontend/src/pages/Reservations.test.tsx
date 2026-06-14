import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Reservations from './Reservations';

// ISSUE-069 — a restaurant host books a table ahead and queues + seats walk-ins.
// The page reads the gated /api/v1/restaurant surface; this test drives the two
// acceptance behaviours through the UI: create a reservation, and seat a queued
// waitlist party to a free table.

const BASE = 'http://127.0.0.1:8000';

const TABLES = [
  { id: 1, name: 'T1', seats: 4, state: 'free', current_ticket_id: null, next_reservation: null },
  { id: 2, name: 'T2', seats: 2, state: 'free', current_ticket_id: null, next_reservation: null },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Reservations />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Reservations & waitlist', () => {
  it('books a table for a given time (AC1)', async () => {
    let posted: Record<string, unknown> | null = null;
    const reservations: Array<Record<string, unknown>> = [];
    server.use(
      http.get(`${BASE}/api/v1/restaurant/tables`, () =>
        HttpResponse.json({ items: TABLES, total: TABLES.length })
      ),
      http.get(`${BASE}/api/v1/restaurant/reservations`, () =>
        HttpResponse.json({ items: reservations, total: reservations.length })
      ),
      http.get(`${BASE}/api/v1/restaurant/waitlist`, () => HttpResponse.json({ items: [], total: 0 })),
      http.post(`${BASE}/api/v1/restaurant/reservations`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        const created = { id: 9, status: 'booked', ...posted };
        reservations.push(created);
        return HttpResponse.json(created, { status: 201 });
      })
    );

    renderPage();

    const dt = await screen.findByLabelText(/date & time/i);
    await userEvent.type(dt, '2026-12-31T19:30');
    // Both forms expose a "customer name" field; the first is the reservation form.
    await userEvent.type(screen.getAllByLabelText(/customer name/i)[0], 'Al-Otaibi');
    await userEvent.click(screen.getByRole('button', { name: /add reservation/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.reserved_at).toBe('2026-12-31T19:30');
    expect(posted!.customer_name).toBe('Al-Otaibi');
    expect(await screen.findByText('Al-Otaibi')).toBeInTheDocument();
  });

  it('seats a queued walk-in to a free table (AC2)', async () => {
    let seatedTable: number | null = null;
    const waitlist: Array<Record<string, unknown>> = [
      { id: 5, customer_name: 'Walk-in', party_size: 3, status: 'waiting' },
    ];
    server.use(
      http.get(`${BASE}/api/v1/restaurant/tables`, () =>
        HttpResponse.json({ items: TABLES, total: TABLES.length })
      ),
      http.get(`${BASE}/api/v1/restaurant/reservations`, () =>
        HttpResponse.json({ items: [], total: 0 })
      ),
      http.get(`${BASE}/api/v1/restaurant/waitlist`, () =>
        HttpResponse.json({ items: waitlist.filter((w) => w.status === 'waiting'), total: 0 })
      ),
      http.post(`${BASE}/api/v1/restaurant/waitlist/:id/seat`, async ({ request, params }) => {
        const body = (await request.json()) as { table_id: number };
        seatedTable = body.table_id;
        waitlist[0].status = 'seated';
        return HttpResponse.json({
          entry: { id: Number(params.id), status: 'seated', seated_table_id: body.table_id },
          ticket: { id: 31, table_id: body.table_id, status: 'open' },
        });
      })
    );

    renderPage();

    const seatSelect = await screen.findByLabelText(/seat at table 5/i);
    await userEvent.selectOptions(seatSelect, '2');

    await waitFor(() => expect(seatedTable).toBe(2));
  });
});
