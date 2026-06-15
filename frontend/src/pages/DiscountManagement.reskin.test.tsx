import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DiscountManagement from './DiscountManagement';

// ISSUE-088 — re-skin + i18n/RTL for DiscountManagement. The page must mirror the
// reference pattern (CustomerManagement / SupplierManagement): loading/empty/
// error/permission states, brand tokens, and fully-translated strings via t()
// across all four languages with RTL for ar/ur.

const BASE = 'http://127.0.0.1:8000';
const EMPTY = { items: [], total: 0 };

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
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DiscountManagement states (UX-02)', () => {
  it('shows the in-page permission state — not the error state — when the discounts fetch 403s', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/discounts`, () => new HttpResponse(null, { status: 403 }))
    );

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // It must NOT fall through to the empty "No discounts created yet" table.
    expect(screen.queryByText(/no discounts created yet/i)).not.toBeInTheDocument();
  });

  it('shows the error state — not the empty state — when the discounts fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/api/v1/entities/discounts`, () => {
        attempt += 1;
        // Fail the first load; succeed (empty) once the user hits Retry.
        if (attempt === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json(EMPTY);
      })
    );

    renderPage();

    // ErrorState renders with role="alert" (distinct from the empty table).
    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    // After a successful retry the error clears and the empty table shows.
    expect(await screen.findByText(/no discounts created yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(EMPTY)));

      const { container } = renderPage();

      // Arabic empty-state copy (not the English "No discounts created yet").
      expect(await screen.findByText('لا توجد خصومات بعد')).toBeInTheDocument();
      // Arabic create-discount action (not the English "Create Discount").
      expect(screen.getByRole('button', { name: /إنشاء خصم/ })).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
