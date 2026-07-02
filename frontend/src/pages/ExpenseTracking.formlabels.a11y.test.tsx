import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ExpenseTracking from './ExpenseTracking';

// ISSUE-226 (a11y · SR pass) — the Expense add/edit form (`renderForm`) painted
// each field's caption as a bare <label> with no `htmlFor`, sitting as a sibling
// of its <Input>/<Select> rather than tied to it. Nothing associated caption to
// control, so the fields had NO accessible name — a placeholder ("0.00") is not a
// name (WCAG 4.1.2). A screen-reader bookkeeper adding an expense heard only
// "edit text" with no way to tell the amount field from the description field.
// Each control must derive its accessible name from its visible caption via a
// proper for/id association.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/entities/expenses`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
    http.get(`${BASE}/api/v1/pos/transactions`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  );
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ExpenseTracking />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ExpenseTracking form input labelling a11y (ISSUE-226)', () => {
  it('names each expense-form control from its visible caption', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /add expense/i }));

    // Each caption must resolve to its own control via a for/id association —
    // placeholder text is not an accessible name.
    expect(screen.getByLabelText(/Category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Amount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Date$/i)).toBeInTheDocument();
  });
});
