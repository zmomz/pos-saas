import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CustomerManagement from './CustomerManagement';

// #273 (Productivity follow-up) — the saved-filter machinery (SavedFilterBar +
// useSavedFilters), wired only on ProductManagement, is reusable. Extend it to
// the Customers book so a power user can pin a search+segment combination and
// re-apply it in one click, surviving a reload.

const BASE = 'http://127.0.0.1:8000';

const TWO_CUSTOMERS = {
  items: [
    {
      id: 'c1',
      name: 'Layla Hassan',
      phone: '+966500000001',
      email: 'layla@example.com',
      vat_number: '300000000000003',
      marketing_consent: true,
      tags: ['vip'],
      pii_erased_at: null,
    },
    {
      id: 'c2',
      name: 'Omar Ali',
      phone: '+966500000002',
      email: 'omar@example.com',
      vat_number: null,
      marketing_consent: false,
      tags: ['wholesale'],
      pii_erased_at: null,
    },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CustomerManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => localStorage.clear());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('CustomerManagement saved filters (#273)', () => {
  it('saves the current search combination and re-applies it in one click', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS))
    );

    const user = userEvent.setup();
    const { container } = renderPage();

    const table = () => container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(await screen.findByText('Layla Hassan')).toBeInTheDocument();

    // Narrow the book to Layla, then pin that view under a name.
    const searchBox = screen.getByPlaceholderText(/search by name/i);
    await user.type(searchBox, 'Layla');
    expect(within(table()).queryByText('Omar Ali')).not.toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText(/name this view/i);
    await user.type(nameInput, 'VIPs');
    await user.click(screen.getByRole('button', { name: /save view/i }));

    // Clear the search — both customers return.
    await user.clear(searchBox);
    expect(within(table()).getByText('Omar Ali')).toBeInTheDocument();

    // One click on the saved chip restores the search and its filtering.
    await user.click(screen.getByRole('button', { name: /apply saved view VIPs/i }));
    expect((searchBox as HTMLInputElement).value).toBe('Layla');
    expect(within(table()).getByText('Layla Hassan')).toBeInTheDocument();
    expect(within(table()).queryByText('Omar Ali')).not.toBeInTheDocument();
  });

  it('persists saved views across a remount (localStorage)', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS))
    );

    const user = userEvent.setup();
    const first = renderPage();
    await screen.findByText('Layla Hassan');

    await user.type(screen.getByPlaceholderText(/search by name/i), 'Omar');
    await user.type(screen.getByPlaceholderText(/name this view/i), 'Wholesale');
    await user.click(screen.getByRole('button', { name: /save view/i }));
    first.unmount();

    // A fresh mount reads the persisted preset back.
    renderPage();
    await screen.findByText('Layla Hassan');
    expect(
      await screen.findByRole('button', { name: /apply saved view Wholesale/i })
    ).toBeInTheDocument();
  });
});
