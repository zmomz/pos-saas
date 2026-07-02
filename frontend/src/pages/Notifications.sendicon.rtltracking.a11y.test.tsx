import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The notifications
// composer uses the lucide `Send` glyph (a paper plane pointing toward the reading
// direction) on both the header "Compose" trigger and the dialog "Send" action.
// A lucide icon is an inline SVG the browser does NOT mirror under `[dir="rtl"]`,
// so an Arabic/Urdu reader (who scans right-to-left) sees the plane fly *backwards*.
// Per Material Design bidirectionality, the send icon is mirrored in RTL; the
// dashboards' idiom is Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180` too).

const LIST_URL = 'http://127.0.0.1:8000/api/v1/notifications/list';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Notifications />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notifications send-icon RTL mirroring (ISSUE-226)', () => {
  it('mirrors the paper-plane on both the compose trigger and the send action', async () => {
    server.use(
      http.get(LIST_URL, () => HttpResponse.json({ items: [], unread_count: 0 }))
    );

    renderPage();
    const user = userEvent.setup();

    // Header "Compose" trigger.
    const compose = await screen.findByRole('button', { name: /compose/i });
    expect(isMirrored(compose.querySelector('svg'))).toBe(true);

    // Dialog "Send" action (default composer state shows the Send glyph, not the
    // CalendarClock scheduled variant).
    await user.click(compose);
    const send = await screen.findByRole('button', { name: /^send$/i });
    expect(isMirrored(send.querySelector('svg'))).toBe(true);
  });
});
