import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import WebhookManagement from './WebhookManagement';

// ISSUE-090 — re-skin + i18n/RTL for WebhookManagement. The page must mirror the
// reference pattern (CustomerManagement / SupplierManagement): loading/empty/
// error/permission states, brand tokens, and fully-translated strings via t()
// across all four languages with RTL for ar/ur.

const BASE = 'http://127.0.0.1:8000/api/v1';
const WEBHOOKS_URL = `${BASE}/entities/webhooks`;
const LOGS_URL = `${BASE}/production/webhooks/logs`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <WebhookManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('WebhookManagement states (UX-02)', () => {
  it('shows the in-page permission state — not the error/empty state — when the webhooks fetch 403s', async () => {
    server.use(
      http.get(WEBHOOKS_URL, () => new HttpResponse(null, { status: 403 }))
    );

    renderPage();

    // PermissionDenied renders "You don't have access"; ErrorState is role=alert.
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // It must NOT fall through to the empty "No webhooks configured yet" view.
    expect(screen.queryByText(/no webhooks configured yet/i)).not.toBeInTheDocument();
  });

  it('shows the error state — not the empty view — when the webhooks fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(WEBHOOKS_URL, () => {
        attempt += 1;
        // Fail the first load; succeed (empty) once the user hits Retry.
        if (attempt === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json({ items: [] });
      }),
      http.get(LOGS_URL, () => HttpResponse.json({ items: [] }))
    );

    renderPage();

    // ErrorState renders with role="alert" (distinct from the empty view).
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    // After a successful retry the error clears and the empty state shows.
    expect(await screen.findByText(/no webhooks configured yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    try {
      server.use(
        http.get(WEBHOOKS_URL, () => HttpResponse.json({ items: [] })),
        http.get(LOGS_URL, () => HttpResponse.json({ items: [] }))
      );

      const { container } = renderPage();

      // Arabic empty-state copy (not the English "No webhooks configured yet").
      expect(await screen.findByText('لا توجد خطافات ويب مُهيأة بعد')).toBeInTheDocument();
      // Arabic "Add Webhook" action (not the English literal).
      expect(screen.getByText('إضافة خطاف ويب')).toBeInTheDocument();
      // RTL is applied for Arabic.
      expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('pos-language');
    }
  });
});
