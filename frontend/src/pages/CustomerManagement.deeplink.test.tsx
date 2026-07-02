import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CustomerManagement from './CustomerManagement';

// #273 (Productivity follow-up — global-search deep-linking): a ⌘K customer hit
// deep-links to /customers?q=<phone|email|name>. Landing there must seed the
// book's search so it narrows to that one record instead of the whole list.

const BASE = 'http://127.0.0.1:8000';

const TWO_CUSTOMERS = {
  items: [
    { id: 'c1', name: 'Layla Hassan', phone: '+966500000001', email: 'layla@example.com', tags: [], pii_erased_at: null },
    { id: 'c2', name: 'Omar Ali', phone: '+966500000002', email: 'omar@example.com', tags: [], pii_erased_at: null },
  ],
  total: 2,
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LanguageProvider>
        <CustomerManagement />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('CustomerManagement deep-link (#273)', () => {
  it('seeds the search from ?q= and narrows to the linked customer', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS)),
    );
    const { container } = renderAt('/customers?q=%2B966500000002'); // Omar's phone

    expect(await screen.findByText('Omar Ali')).toBeInTheDocument();
    const table = container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(within(table).queryByText('Layla Hassan')).not.toBeInTheDocument();

    const searchBox = screen.getByPlaceholderText(/search by name/i) as HTMLInputElement;
    expect(searchBox.value).toBe('+966500000002');
  });

  it('shows every customer when there is no ?q=', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(TWO_CUSTOMERS)),
    );
    const { container } = renderAt('/customers');

    expect(await screen.findByText('Layla Hassan')).toBeInTheDocument();
    const table = container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(within(table).getByText('Omar Ali')).toBeInTheDocument();
  });
});
