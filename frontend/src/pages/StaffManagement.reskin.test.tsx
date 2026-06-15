import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import StaffManagement from './StaffManagement';

// ISSUE-092 — re-skin + i18n/RTL for StaffManagement. The page must mirror the
// reference pattern (CustomerManagement / SupplierManagement): loading / empty /
// error / permission states, brand tokens, and fully-translated strings via t()
// across all four languages with RTL for ar/ur.

const BASE = 'http://127.0.0.1:8000';
const STAFF_URL = `${BASE}/api/v1/entities/staff_members`;
const EMPTY = { items: [], total: 0, skip: 0, limit: 200 };

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <StaffManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());

describe('StaffManagement states (UX-02)', () => {
  it('shows the in-page permission state — not the error state — when the staff fetch 403s', async () => {
    server.use(http.get(STAFF_URL, () => new HttpResponse(null, { status: 403 })));

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // It must NOT fall through to the empty "No staff members found" table.
    expect(screen.queryByText(/no staff members found/i)).not.toBeInTheDocument();
  });

  it('shows the error state — not the empty state — when the staff fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(STAFF_URL, () => {
        attempt += 1;
        if (attempt === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json(EMPTY);
      })
    );

    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    expect(await screen.findByText(/no staff members found/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(http.get(STAFF_URL, () => HttpResponse.json(EMPTY)));

    const { container } = renderPage();

    // Arabic empty-state copy (not the English "No staff members found").
    expect(await screen.findByText('لا يوجد موظفون')).toBeInTheDocument();
    // Arabic add-staff button (not the English "Add Staff").
    expect(screen.getByRole('button', { name: /إضافة موظف/ })).toBeInTheDocument();
    // RTL is applied for Arabic.
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
  });
});
