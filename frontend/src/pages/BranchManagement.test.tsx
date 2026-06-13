import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BranchManagement from './BranchManagement';

// ISSUE-062 — a merchant designates the main branch (exactly one) from the
// Branch Management screen. The "Set as Main" control POSTs to the dedicated
// set-main endpoint (which unsets the previous main server-side); the branch
// already flagged is_main shows a non-actionable "Main" badge instead.

const BASE = 'http://127.0.0.1:8000';

const TWO_BRANCHES = {
  items: [
    { id: 1, name: 'Downtown', is_active: true, is_main: true },
    { id: 2, name: 'Airport', is_active: true, is_main: false },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <BranchManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BranchManagement main-branch designation (ISSUE-062)', () => {
  it('sets a non-main branch as main via the set-main endpoint', async () => {
    const setMain = vi.fn();
    server.use(
      http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(TWO_BRANCHES)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json({ items: [], total: 0 })),
      http.post(`${BASE}/api/v1/entities/branches/2/set-main`, () => {
        setMain();
        return HttpResponse.json({ id: 2, name: 'Airport', is_active: true, is_main: true });
      })
    );

    renderPage();

    // The Airport card (currently not main) offers a "Set as Main" action.
    const airportCard = (await screen.findByText('Airport')).closest('div[class*="rounded"]') as HTMLElement;
    const setMainBtn = within(airportCard).getByRole('button', { name: /set as main/i });
    await userEvent.click(setMainBtn);

    await waitFor(() => expect(setMain).toHaveBeenCalledTimes(1));
  });

  it('shows a non-actionable Main badge on the branch already flagged main', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(TWO_BRANCHES)),
      http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json({ items: [], total: 0 }))
    );

    renderPage();

    const downtownCard = (await screen.findByText('Downtown')).closest('div[class*="rounded"]') as HTMLElement;
    // The current main shows a "Main" badge and offers no "Set as Main" button.
    expect(within(downtownCard).getByText(/^Main$/)).toBeInTheDocument();
    expect(within(downtownCard).queryByRole('button', { name: /set as main/i })).not.toBeInTheDocument();
  });
});
