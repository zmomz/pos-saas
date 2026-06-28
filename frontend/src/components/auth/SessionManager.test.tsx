import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SessionManager from './SessionManager';

// ISSUE-202 — the Security card now lists REAL sessions and revokes them, instead
// of a hardcoded "Current Session — Active now" row that always claimed one
// session regardless of reality.
const BASE = 'http://127.0.0.1:8000/api/v1';

function renderManager() {
  return render(
    <LanguageProvider>
      <SessionManager />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SessionManager', () => {
  it('lists real sessions and flags the current device', async () => {
    server.use(
      http.get(`${BASE}/auth/sessions`, () =>
        HttpResponse.json({
          sessions: [
            {
              id: 's1',
              current: true,
              user_agent: 'Mozilla/5.0 (Windows NT 10.0) Chrome/120',
              ip_address: '10.0.0.1',
              created_at: null,
              last_used_at: '2026-06-01T10:00:00Z',
            },
            {
              id: 's2',
              current: false,
              user_agent: 'Mozilla/5.0 (iPhone) Safari/17',
              ip_address: '10.0.0.2',
              created_at: null,
              last_used_at: '2026-05-20T08:00:00Z',
            },
          ],
        })
      )
    );

    renderManager();

    expect(await screen.findByText(/This device/i)).toBeInTheDocument();
    expect(screen.getByText(/Chrome · Windows/)).toBeInTheDocument();
    expect(screen.getByText(/Safari · iOS/)).toBeInTheDocument();
    // The current session is not revocable; the other one is.
    expect(screen.getByRole('button', { name: /^Revoke$/i })).toBeInTheDocument();
  });

  it('revokes a non-current session after confirmation and reloads', async () => {
    let deleted: string | null = null;
    let listCalls = 0;
    server.use(
      http.get(`${BASE}/auth/sessions`, () => {
        listCalls += 1;
        const sessions = [
          { id: 's1', current: true, user_agent: 'Chrome', ip_address: null, created_at: null, last_used_at: null },
        ];
        if (listCalls === 1) {
          sessions.push({
            id: 's2',
            current: false,
            user_agent: 'Firefox',
            ip_address: null,
            created_at: null,
            last_used_at: null,
          });
        }
        return HttpResponse.json({ sessions });
      }),
      http.delete(`${BASE}/auth/sessions/:id`, ({ params }) => {
        deleted = params.id as string;
        return HttpResponse.json({ success: true, revoked: 1 });
      })
    );

    const user = userEvent.setup();
    renderManager();

    await user.click(await screen.findByRole('button', { name: /^Revoke$/i }));

    // Confirm in the dialog.
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /Sign out/i }));

    await waitFor(() => expect(deleted).toBe('s2'));
    // After revoke it reloads; the second fetch drops s2.
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2));
  });

  it('shows the error state with a retry when the list fails', async () => {
    server.use(
      http.get(`${BASE}/auth/sessions`, () => new HttpResponse(null, { status: 500 }))
    );
    renderManager();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
