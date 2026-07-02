import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-226 (a11y · SR pass) — the "Add station" dialog rendered each field's
// caption as a bare <label> with no `htmlFor`, so it was never programmatically
// tied to its <Input>. A placeholder is not an accessible name (WCAG 4.1.2), so
// a screen-reader cook heard only "edit text" with no idea which field held the
// station name vs. its Arabic name. Each input must derive its accessible name
// from the visible label via a proper for/id association.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json([])),
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

describe('KDS add-station dialog input labelling a11y (ISSUE-226)', () => {
  it('names each station-form input from its visible label', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /add station/i }));

    // Each caption must resolve to its own field via a for/id association —
    // placeholder text ("Grill") is not an accessible name.
    expect(screen.getByLabelText(/^Station name$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Station name \(Arabic\)/i)).toBeInTheDocument();
  });
});
