import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import KDS from './KDS';

// ISSUE-244 — the add-station example placeholders ("Grill" / "الشواية") were
// single-language regardless of the UI locale. They must route through tt() so
// an ar user sees an Arabic hint, not a stray English word.

const BASE = 'http://127.0.0.1:8000';
const STATIONS = [{ id: 1, name: 'Grill', name_ar: 'الشواية' }];

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  localStorage.removeItem('pos-language');
});
afterAll(() => server.close());

function mock() {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/kds/stations`, () => HttpResponse.json(STATIONS)),
    http.get(`${BASE}/api/v1/restaurant/kds/tickets`, () => HttpResponse.json({ items: [], total: 0 }))
  );
}

describe('KDS add-station placeholders localize (ISSUE-244)', () => {
  it('does not show the hardcoded English "Grill" placeholder in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    mock();
    render(
      <LanguageProvider>
        <KDS />
      </LanguageProvider>
    );
    const addBtn = await screen.findByRole('button', { name: /إضافة محطة|محطة/ });
    await userEvent.click(addBtn);

    // The station-name input must not carry the bare English "Grill" placeholder.
    expect(screen.queryByPlaceholderText('Grill')).toBeNull();
    // It should carry the localized example instead.
    expect(screen.getByPlaceholderText('الشواية')).toBeInTheDocument();
  });
});
