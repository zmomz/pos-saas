import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CustomerManagement from './CustomerManagement';

// ISSUE-272 (M7·Compliance) — the backend-only consent-history and
// retention-policy endpoints must have a frontend surface. Fetches are lazy
// (opened from a button) so the page mount is unchanged.

const BASE = 'http://127.0.0.1:8000';

const ONE_CUSTOMER = {
  items: [
    {
      id: 'c1',
      name: 'Layla Hassan',
      phone: '+966500000001',
      email: 'layla@example.com',
      marketing_consent: true,
      tags: [],
      pii_erased_at: null,
    },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CustomerManagement />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('CustomerManagement — consent-history viewer (#272)', () => {
  it('opens a per-customer consent trail and lists each change', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(ONE_CUSTOMER)),
      http.get(`${BASE}/api/v1/entities/customers/c1/consent-history`, () =>
        HttpResponse.json({
          customer_id: 1,
          items: [
            {
              id: 2,
              consent_type: 'marketing',
              granted: false,
              source: 'update',
              actor: 'owner',
              created_at: '2026-02-01T10:00:00Z',
            },
            {
              id: 1,
              consent_type: 'marketing',
              granted: true,
              source: 'create',
              actor: 'owner',
              created_at: '2026-01-01T10:00:00Z',
            },
          ],
        }),
      ),
    );

    renderPage();
    await screen.findByText('Layla Hassan');

    await userEvent.click(screen.getByRole('button', { name: /consent history/i }));

    const dialog = await screen.findByRole('dialog');
    // Newest-first: the withdrawal and the original grant both surface.
    expect(within(dialog).getByText(/withdrawn/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/granted/i)).toBeInTheDocument();
  });
});

describe('CustomerManagement — retention-policy config (#272)', () => {
  it('shows the current window and saves a new one', async () => {
    let putBody: unknown = null;
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(ONE_CUSTOMER)),
      http.get(`${BASE}/api/v1/entities/customers/retention-policy`, () =>
        HttpResponse.json({ customer_pii_retention_days: 90, updated_at: '2026-06-01T00:00:00Z' }),
      ),
      http.put(`${BASE}/api/v1/entities/customers/retention-policy`, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({
          customer_pii_retention_days: 30,
          updated_at: '2026-07-02T00:00:00Z',
        });
      }),
    );

    renderPage();
    await screen.findByText('Layla Hassan');

    await userEvent.click(screen.getByRole('button', { name: /data retention/i }));

    // The dialog loads and shows the current 90-day window.
    const dialog = await screen.findByRole('dialog');
    const input = await within(dialog).findByDisplayValue('90');

    await userEvent.clear(input);
    await userEvent.type(input, '30');
    await userEvent.click(within(dialog).getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(putBody).toEqual({ customer_pii_retention_days: 30 }),
    );
  });
});
