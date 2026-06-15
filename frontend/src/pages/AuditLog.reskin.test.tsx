import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AuditLog from './AuditLog';

// ISSUE-089 — re-skin + i18n/RTL for AuditLog. The page must mirror the reference
// pattern (CustomerManagement / SupplierManagement): loading/empty/error/permission
// states, brand tokens, and fully-translated strings via t() across all four
// languages with RTL for ar/ur.

const BASE = 'http://127.0.0.1:8000';
const EMPTY = { items: [], total: 0, skip: 0, limit: 200 };

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AuditLog />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AuditLog states (UX-02)', () => {
  it('shows the in-page permission state — not the error/empty state — when the fetch 403s', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => new HttpResponse(null, { status: 403 }))
    );

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // It must NOT fall through to the empty "No audit entries" table.
    expect(screen.queryByText(/no audit entries/i)).not.toBeInTheDocument();
  });

  it('shows the error state — not the empty state — when the fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => {
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

    // After a successful retry the error clears and the empty state shows.
    expect(await screen.findByText(/no audit entries/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json(EMPTY)));

      const { container } = renderPage();

      // Arabic header title (not the English "Audit Log").
      expect(await screen.findByText('سجل المراجعة')).toBeInTheDocument();
      // Arabic empty-state copy (not the English "No audit entries").
      expect(screen.getByText('لا توجد سجلات تدقيق بعد.')).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
