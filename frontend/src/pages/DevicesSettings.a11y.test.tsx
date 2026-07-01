import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DevicesSettings from './DevicesSettings';

// ISSUE-226 (M11 FE-Platform · a11y) — the add-terminal dialog renders a *visible*
// <Label> above each text field, but the Labels were never programmatically
// associated with their <Input> (no htmlFor/id). A screen-reader user tabbing into
// the field heard only "edit text" — a placeholder is not a robust accessible name.
// WCAG 1.3.1 (info & relationships) / 3.3.2 (labels or instructions). Every field
// must expose its accessible name so getByLabelText can reach it. Same defect class
// as the printer-settings fix.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DevicesSettings />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DevicesSettings form field labelling (ISSUE-226 a11y)', () => {
  it('exposes each add-terminal text field by its visible label as accessible name', async () => {
    server.use(http.get(`${BASE}/api/v1/payments/terminals`, () => HttpResponse.json([])));

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /add terminal/i }));
    const dialog = await screen.findByRole('dialog');

    for (const label of [/terminal name/i, /serial number/i, /branch id/i]) {
      const input = within(dialog).getByLabelText(label);
      expect(input.tagName).toBe('INPUT');
    }
  });
});
