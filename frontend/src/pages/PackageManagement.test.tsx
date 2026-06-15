import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PackageManagement from './PackageManagement';

// ISSUE-085 — re-skin + i18n/RTL for PackageManagement. The page must mirror the
// reference pattern (CustomerManagement / Notifications): loading/empty/error/
// permission states, brand tokens, and fully-translated strings via t() across
// all four languages with RTL for ar/ur.

const URL = 'http://127.0.0.1:8000/api/v1/packages/list';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <PackageManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PackageManagement states (UX-02)', () => {
  it('shows the in-page permission state — not the error state — when the fetch 403s', async () => {
    server.use(http.get(URL, () => new HttpResponse(null, { status: 403 })));

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders the empty state translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(http.get(URL, () => HttpResponse.json({ items: [], total: 0 })));

      const { container } = renderPage();

      // Arabic empty-catalog copy (not the English "No packages found").
      expect(await screen.findByText('لا توجد باقات')).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
