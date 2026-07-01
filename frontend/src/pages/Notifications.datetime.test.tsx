import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';
import Notifications from './Notifications';

// #208 (M11 FE-Platform) — single money/date formatting path. The feed's
// per-notification timestamp previously rendered through a bespoke
// `new Date(...).toLocaleString(...)` helper that emitted Arabic-Indic digits
// for ar-SA and a non-shared "medium/short" format. It must route through the
// shared `formatDateTime` helper (Gregorian, Western numerals in every
// language) so there is one date path. Fails before the migration.

const URL = 'http://127.0.0.1:8000/api/v1/notifications/list';
const CREATED_AT = '2026-06-03T10:00:00Z';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Notifications />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notifications timestamp uses the shared formatDateTime path (#208)', () => {
  it('renders the notification timestamp exactly as the shared helper does', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({
          items: [
            {
              id: '9',
              type: 'low_stock',
              title: 'Low Stock Alert',
              message: 'Sugar has only 3 units remaining',
              is_read: false,
              created_at: CREATED_AT,
            },
          ],
          unread_count: 1,
        })
      )
    );

    renderPage();

    // Default language is 'en'. The rendered timestamp must equal the shared
    // helper's output (dd/mm/yyyy, hh:mm) — not the old bespoke toLocaleString
    // "Jun 3, 2026, 10:00 AM" format.
    const expected = formatDateTime(CREATED_AT, 'en');
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
});
