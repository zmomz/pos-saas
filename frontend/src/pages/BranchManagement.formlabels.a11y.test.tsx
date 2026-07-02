import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BranchManagement from './BranchManagement';

// ISSUE-226 (a11y · SR pass) — the Branch add/edit form (`renderForm`, reused by
// both the "Add New Branch" and "Edit Branch" dialogs) painted each field's
// caption as a bare <label> with no `htmlFor`, sitting as a sibling of its
// <Input> rather than tied to it. Nothing associated caption to control, so the
// four fields had NO accessible name — a placeholder ("Main Branch") is not a
// name (WCAG 4.1.2). A screen-reader operator adding a branch heard only "edit
// text" with no way to tell the name field from address, manager, or phone.
// Each control must derive its accessible name from its visible caption via a
// proper for/id association.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/entities/branches`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
    http.get(`${BASE}/api/v1/entities/products`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
  return render(
    <LanguageProvider>
      <BranchManagement />
    </LanguageProvider>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BranchManagement form input labelling a11y (ISSUE-226)', () => {
  it('names each branch-form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /add branch/i }));

    // Each caption must resolve to its own control via a for/id association —
    // placeholder text is not an accessible name.
    expect(screen.getByLabelText(/Branch Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Address$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Manager Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Phone$/i)).toBeInTheDocument();
  });
});
