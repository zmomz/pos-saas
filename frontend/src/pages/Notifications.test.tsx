import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// F-051 (UX-02): a failed notifications fetch previously did `catch { setNotifications([]) }`
// — a 500 looked identical to "No notifications". This test renders the page
// against a failing endpoint and asserts a real error state shows instead of the
// empty state; and a 403 shows the in-page permission state. It fails before the fix.

const URL = 'http://127.0.0.1:8000/api/v1/notifications/list';

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

describe('Notifications surfaces errors distinct from empty (F-051 / UX-02)', () => {
  it('shows an error state — not the empty state — when the fetch 500s', async () => {
    server.use(http.get(URL, () => new HttpResponse(null, { status: 500 })));

    renderPage();

    // The shared ErrorState is an alert role.
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('No notifications')).not.toBeInTheDocument();
  });

  it('shows the in-page permission state when the fetch 403s', async () => {
    server.use(http.get(URL, () => new HttpResponse(null, { status: 403 })));

    renderPage();

    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByText('No notifications')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the empty state when the fetch succeeds with no notifications', async () => {
    server.use(
      http.get(URL, () => HttpResponse.json({ items: [], unread_count: 0 }))
    );

    renderPage();

    expect(await screen.findByText('No notifications')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  // F-052 (UX-08): the backend returns { items, unread_count } but the page read
  // `data.notifications` — so the feed ALWAYS rendered empty regardless of the
  // alerts returned. This pins the `items → notifications` mapping: a populated
  // feed must actually render. Fails before the api.ts fix.
  it('renders the feed when the backend returns items (not the empty state)', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({
          items: [
            {
              id: '7',
              type: 'low_stock',
              title: 'Low Stock Alert',
              message: 'Sugar has only 3 units remaining',
              is_read: false,
              created_at: '2026-06-03T10:00:00Z',
            },
          ],
          unread_count: 1,
        })
      )
    );

    renderPage();

    expect(await screen.findByText('Sugar has only 3 units remaining')).toBeInTheDocument();
    expect(screen.queryByText('No notifications')).not.toBeInTheDocument();
  });
});
