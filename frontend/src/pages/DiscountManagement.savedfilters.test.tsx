import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DiscountManagement from './DiscountManagement';

// #273 (Productivity follow-up) — the saved-filter machinery (SavedFilterBar +
// useSavedFilters), wired on ProductManagement and the Customers book, is
// reusable. Extend it to the Discounts book so a power user can pin a
// code-search + status-segment combination and re-apply it in one click,
// surviving a reload. Doing so first gives Discounts the search + status filter
// it lacked.

const BASE = 'http://127.0.0.1:8000';

const LIST = {
  items: [
    { id: 'd1', code: 'SUMMER10', type: 'percentage', value: 10, is_active: true },
    { id: 'd2', code: 'WINTER20', type: 'percentage', value: 20, is_active: false },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DiscountManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => localStorage.clear());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DiscountManagement saved filters (#273)', () => {
  it('narrows the book by code search', async () => {
    server.use(http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)));

    const user = userEvent.setup();
    const { container } = renderPage();
    const table = () => container.querySelector('table.dxr-tbl') as HTMLElement;

    expect(await screen.findByText('SUMMER10')).toBeInTheDocument();
    expect(within(table()).getByText('WINTER20')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/search by code/i), 'SUMMER');
    expect(within(table()).getByText('SUMMER10')).toBeInTheDocument();
    expect(within(table()).queryByText('WINTER20')).not.toBeInTheDocument();
  });

  it('saves the current search combination and re-applies it in one click', async () => {
    server.use(http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)));

    const user = userEvent.setup();
    const { container } = renderPage();
    const table = () => container.querySelector('table.dxr-tbl') as HTMLElement;

    expect(await screen.findByText('SUMMER10')).toBeInTheDocument();

    // Narrow the book to the summer code, then pin that view under a name.
    const searchBox = screen.getByPlaceholderText(/search by code/i);
    await user.type(searchBox, 'SUMMER');
    expect(within(table()).queryByText('WINTER20')).not.toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText(/name this view/i);
    await user.type(nameInput, 'Seasonal');
    await user.click(screen.getByRole('button', { name: /save view/i }));

    // Clear the search — both discounts return.
    await user.clear(searchBox);
    expect(within(table()).getByText('WINTER20')).toBeInTheDocument();

    // One click on the saved chip restores the search and its filtering.
    await user.click(screen.getByRole('button', { name: /apply saved view Seasonal/i }));
    expect((searchBox as HTMLInputElement).value).toBe('SUMMER');
    expect(within(table()).getByText('SUMMER10')).toBeInTheDocument();
    expect(within(table()).queryByText('WINTER20')).not.toBeInTheDocument();
  });

  it('captures the status segment in a saved view', async () => {
    server.use(http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)));

    const user = userEvent.setup();
    const { container } = renderPage();
    const table = () => container.querySelector('table.dxr-tbl') as HTMLElement;

    expect(await screen.findByText('SUMMER10')).toBeInTheDocument();

    // Filter to inactive-only, then pin it.
    await user.click(screen.getByRole('button', { name: /^inactive$/i }));
    expect(within(table()).queryByText('SUMMER10')).not.toBeInTheDocument();
    expect(within(table()).getByText('WINTER20')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/name this view/i), 'Retired');
    await user.click(screen.getByRole('button', { name: /save view/i }));

    // Reset to all statuses, then re-apply — the segment comes back.
    await user.click(screen.getByRole('button', { name: /^all$/i }));
    expect(within(table()).getByText('SUMMER10')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /apply saved view Retired/i }));
    expect(within(table()).queryByText('SUMMER10')).not.toBeInTheDocument();
    expect(within(table()).getByText('WINTER20')).toBeInTheDocument();
  });

  it('persists saved views across a remount (localStorage)', async () => {
    server.use(http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(LIST)));

    const user = userEvent.setup();
    const first = renderPage();
    await screen.findByText('SUMMER10');

    await user.type(screen.getByPlaceholderText(/search by code/i), 'WINTER');
    await user.type(screen.getByPlaceholderText(/name this view/i), 'Cold');
    await user.click(screen.getByRole('button', { name: /save view/i }));
    first.unmount();

    // A fresh mount reads the persisted preset back.
    renderPage();
    await screen.findByText('SUMMER10');
    expect(
      await screen.findByRole('button', { name: /apply saved view Cold/i })
    ).toBeInTheDocument();
  });
});
