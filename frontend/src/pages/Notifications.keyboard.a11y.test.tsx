import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// A11y keyboard audit (ISSUE-226 · M11 FE-Platform). Each unread notification
// tile marks itself read on click, but it was a bare `<div onClick>` — no role,
// no tabIndex, no keyboard handler. A keyboard-only or screen-reader user could
// neither reach it nor activate it (WCAG 2.1.1 Keyboard / 4.1.2 Name, Role,
// Value). These tests pin the tile as a real, keyboard-operable control.

const LIST_URL = 'http://127.0.0.1:8000/api/v1/notifications/list';
const MARK_URL = 'http://127.0.0.1:8000/api/v1/notifications/mark-read';

const UNREAD = {
  id: '7',
  type: 'low_stock',
  title: 'Low Stock Alert',
  message: 'Sugar has only 3 units remaining',
  is_read: false,
  created_at: '2026-06-03T10:00:00Z',
};

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

describe('Notifications tiles are keyboard-operable (ISSUE-226 a11y)', () => {
  it('exposes an unread tile as a focusable button with an accessible name', async () => {
    server.use(http.get(LIST_URL, () => HttpResponse.json({ items: [UNREAD], unread_count: 1 })));

    renderPage();

    const tile = await screen.findByRole('button', { name: /Sugar has only 3 units remaining/ });
    expect(tile).toHaveAttribute('tabindex', '0');
  });

  it('marks an unread tile read when activated with the Enter key', async () => {
    let marked: string | null = null;
    server.use(
      http.get(LIST_URL, () => HttpResponse.json({ items: [UNREAD], unread_count: 1 })),
      http.post(MARK_URL, async ({ request }) => {
        const body = (await request.json()) as { notification_id: string };
        marked = body.notification_id;
        return HttpResponse.json({ ok: true });
      })
    );

    renderPage();

    const tile = await screen.findByRole('button', { name: /Sugar has only 3 units remaining/ });
    fireEvent.keyDown(tile, { key: 'Enter' });

    await screen.findByRole('button', { name: /Sugar has only 3 units remaining/ });
    expect(marked).toBe('7');
  });
});
