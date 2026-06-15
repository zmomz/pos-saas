import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BrandingEditor from './BrandingEditor';

// ISSUE-086 — re-skin + i18n/RTL for BrandingEditor. The page must mirror the
// reference pattern (CustomerManagement / PackageManagement): loading/error/
// permission states, brand tokens, and fully-translated strings via t() across
// all four languages with RTL for ar/ur. There is no list, so no empty state.

const URL = 'http://127.0.0.1:8000/api/v1/tenant/agent/branding';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <BrandingEditor />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BrandingEditor states (UX-02)', () => {
  it('shows the in-page permission state — not the editor — when the fetch 403s', async () => {
    server.use(http.get(URL, () => new HttpResponse(null, { status: 403 })));

    renderPage();

    // PermissionDenied renders "You don't have access".
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    // The editor form must not render behind the permission wall.
    expect(screen.queryByText('Live Preview')).not.toBeInTheDocument();
  });

  it('shows the error state — distinct from a fresh (404) editor — when the fetch 500s', async () => {
    server.use(http.get(URL, () => new HttpResponse(null, { status: 500 })));

    renderPage();

    // ErrorState is role=alert; the editor must not render.
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Live Preview')).not.toBeInTheDocument();
  });

  it('renders the editor with brand-token chrome translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(http.get(URL, () => HttpResponse.json({})));

      const { container } = renderPage();

      // Arabic "Live Preview" copy (not the English string).
      expect(await screen.findByText('معاينة مباشرة')).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
