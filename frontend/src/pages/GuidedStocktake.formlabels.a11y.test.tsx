import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import GuidedStocktake from './GuidedStocktake';

// ISSUE-226 (a11y · SR pass) — the "Start stocktake" dialog painted each field's
// caption as a bare <label> with no `htmlFor`, sitting as a sibling of its
// <Select>/<Input> rather than tied to it. Nothing associated caption to
// control, so the branch-scope picker and the name field had NO accessible name
// (WCAG 4.1.2). A screen-reader operator starting a count heard only "edit
// text" / an unnamed combobox with no way to tell the branch picker from the
// name field. Each control must derive its accessible name from its visible
// caption via a proper for/id association.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/production/stock-counts`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
    http.get(`${BASE}/api/v1/entities/branches`, () =>
      HttpResponse.json({ items: [{ id: 1, name: 'Main Branch' }], total: 1 }),
    ),
  );
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <GuidedStocktake />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('GuidedStocktake form input labelling a11y (ISSUE-226)', () => {
  it('names each start-stocktake form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    const triggers = await screen.findAllByRole('button', { name: /start stocktake/i });
    await user.click(triggers[0]);

    // Each caption must resolve to its own control via a for/id association —
    // placeholder text is not an accessible name.
    expect(screen.getByLabelText(/Branch to count/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Name \(optional\)/i)).toBeInTheDocument();
  });
});
