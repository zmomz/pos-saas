import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PackageManagement from './PackageManagement';

// ISSUE-226 (a11y · SR pass) — the "Add/Edit Package" dialog painted each
// field's caption as a bare <label> with no `htmlFor`, sitting as a sibling of
// its <Input> rather than tied to it. Nothing associated caption to control, so
// Name, Client Slots, Wholesale Price, and Retail Price/Client had NO
// accessible name (WCAG 1.3.1 / 4.1.2). A screen-reader operator authoring a
// package heard only "edit text" with no way to tell the fields apart, and the
// three numeric price/slot spinners were indistinguishable. Each control must
// derive its accessible name from its visible caption via a for/id association;
// a placeholder is not an accessible name.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/packages/list`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <PackageManagement />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PackageManagement form input labelling a11y (ISSUE-226)', () => {
  it('names each add-package form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    const addBtn = await screen.findByRole('button', { name: /add package/i });
    await user.click(addBtn);

    // Each caption must resolve to its own control via a for/id association —
    // placeholder text is not an accessible name.
    expect(screen.getByLabelText(/^Name$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client Slots/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Wholesale Price/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Retail Price\/Client/i)).toBeInTheDocument();
  });
});
