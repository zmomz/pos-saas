import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SupplierManagement from './SupplierManagement';

// ISSUE-087 — re-skin + i18n/RTL for SupplierManagement. The page must mirror the
// reference pattern (CustomerManagement / GiftCardManagement / PackageManagement):
// loading/empty/error/permission states, brand tokens, and fully-translated
// strings via t() across all four languages with RTL for ar/ur.

const BASE = 'http://127.0.0.1:8000';
const EMPTY = { items: [], total: 0 };

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

function stubAuxEndpoints() {
  server.use(
    http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(EMPTY))
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SupplierManagement states (UX-02)', () => {
  it('shows the in-page permission state — not the error state — when the suppliers fetch 403s', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => new HttpResponse(null, { status: 403 }))
    );
    stubAuxEndpoints();

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // It must NOT fall through to the empty "No suppliers found" table.
    expect(screen.queryByText(/no suppliers found/i)).not.toBeInTheDocument();
  });

  it('shows the error state — not the empty state — when the suppliers fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => {
        attempt += 1;
        // Fail the first load; succeed (empty) once the user hits Retry.
        if (attempt === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json(EMPTY);
      })
    );
    stubAuxEndpoints();

    renderPage();

    // ErrorState renders with role="alert" (distinct from the empty table).
    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    // After a successful retry the error clears and the empty table shows.
    expect(await screen.findByText(/no suppliers found/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(EMPTY)));
      stubAuxEndpoints();

      const { container } = renderPage();

      // Arabic empty-state copy (not the English "No suppliers found").
      expect(await screen.findByText('لا يوجد موردون')).toBeInTheDocument();
      // Arabic tab label (not the English "Suppliers").
      expect(screen.getByRole('button', { name: 'الموردون' })).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
