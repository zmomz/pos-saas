import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CustomerManagement from './CustomerManagement';

// #273 (Productivity follow-up — entity-level favorites). Star an individual
// customer so it's one click away later. Stars persist (localStorage) and a
// "Favorites only" filter narrows the book to the starred records.

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

describe('CustomerManagement entity favorites (#273)', () => {
  it('stars a customer and filters the book to favorites only', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS))
    );

    const user = userEvent.setup();
    const { container } = renderPage();

    const table = () => container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(await screen.findByText('Layla Hassan')).toBeInTheDocument();

    // Star Layla via her row's favorite toggle.
    await user.click(screen.getByRole('button', { name: /add to favorites: Layla Hassan/i }));

    // The toggle now reads as pressed / "remove".
    expect(
      screen.getByRole('button', { name: /remove from favorites: Layla Hassan/i })
    ).toHaveAttribute('aria-pressed', 'true');

    // Flip on "Favorites only" — Omar (unstarred) drops out.
    await user.click(screen.getByRole('button', { name: /favorites only/i }));
    expect(within(table()).getByText('Layla Hassan')).toBeInTheDocument();
    expect(within(table()).queryByText('Omar Ali')).not.toBeInTheDocument();

    // Flip it back off — the whole book returns.
    await user.click(screen.getByRole('button', { name: /favorites only/i }));
    expect(within(table()).getByText('Omar Ali')).toBeInTheDocument();
  });

  it('persists stars across a remount (localStorage)', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS))
    );

    const user = userEvent.setup();
    const first = renderPage();
    await screen.findByText('Omar Ali');

    await user.click(screen.getByRole('button', { name: /add to favorites: Omar Ali/i }));
    first.unmount();

    // A fresh mount reads the persisted star back.
    const { container } = renderPage();
    await screen.findByText('Omar Ali');
    expect(
      screen.getByRole('button', { name: /remove from favorites: Omar Ali/i })
    ).toHaveAttribute('aria-pressed', 'true');

    // And the persisted star still drives the favorites-only filter.
    await user.click(screen.getByRole('button', { name: /favorites only/i }));
    const table = container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(within(table).getByText('Omar Ali')).toBeInTheDocument();
    expect(within(table).queryByText('Layla Hassan')).not.toBeInTheDocument();
  });
});
