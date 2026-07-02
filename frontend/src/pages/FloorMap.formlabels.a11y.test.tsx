import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import FloorMap from './FloorMap';

// ISSUE-226 (a11y · SR pass) — the "Add Zone" and "Add Table" dialogs painted
// each field's caption as a bare <label> with no `htmlFor`, sitting as a
// sibling of its <Input>/<Select> rather than tied to it. Nothing associated
// caption to control, so the fields had NO accessible name (WCAG 4.1.2). A
// screen-reader operator adding a zone or table heard only "edit text" with no
// way to tell the name field from seats or the zone picker. Each control must
// derive its accessible name from its visible caption via a for/id association.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/zones`, () =>
      HttpResponse.json([{ id: 1, name: 'Patio' }]),
    ),
    http.get(`${BASE}/api/v1/restaurant/tables`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <FloorMap />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FloorMap form input labelling a11y (ISSUE-226)', () => {
  it('names the add-zone form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /add zone/i }));

    expect(screen.getByLabelText(/Zone Name/i)).toBeInTheDocument();
  });

  it('names each add-table form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /add table/i }));

    expect(screen.getByLabelText(/Table Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Seats$/i)).toBeInTheDocument();
    // The zone picker (a shadcn Select) is only rendered once zones exist.
    expect(screen.getByLabelText(/All Zones/i)).toBeInTheDocument();
  });
});
