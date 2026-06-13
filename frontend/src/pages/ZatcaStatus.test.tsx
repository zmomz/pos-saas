import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ZatcaStatus from './ZatcaStatus';

// F-019 (ZA-08): the ZATCA document-status page must (1) render a real error
// state — distinct from the empty state — when the summary fetch fails, (2) show
// the empty state when there are genuinely no documents, and (3) surface a
// stuck-document alert with a reconcile action when pending/failed > 0.

const SUMMARY = 'http://127.0.0.1:8000/api/v1/zatca/documents/summary';
const DOCS = 'http://127.0.0.1:8000/api/v1/zatca/documents';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ZatcaStatus />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ZatcaStatus (F-019 / ZA-08)', () => {
  it('shows an error state — not the empty state — when the summary fetch 500s', async () => {
    server.use(
      http.get(SUMMARY, () => new HttpResponse(null, { status: 500 })),
      http.get(DOCS, () => HttpResponse.json({ items: [], total: 0 }))
    );

    renderPage();

    expect(await screen.findByText('Could not load ZATCA documents. Please try again.')).toBeInTheDocument();
    expect(screen.queryByText('No fiscal documents yet')).not.toBeInTheDocument();
  });

  it('shows the empty state when there are genuinely no documents', async () => {
    server.use(
      http.get(SUMMARY, () =>
        HttpResponse.json({
          total: 0,
          by_status: {},
          pending: 0,
          failed: 0,
          stuck: 0,
          needs_attention: false,
          onboarded: false,
          gateway_configured: false,
        })
      ),
      http.get(DOCS, () => HttpResponse.json({ items: [], total: 0 }))
    );

    renderPage();

    expect(await screen.findByText('No fiscal documents yet')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces a stuck-document alert with a reconcile action when documents are stuck', async () => {
    server.use(
      http.get(SUMMARY, () =>
        HttpResponse.json({
          total: 3,
          by_status: { signed: 1, pending: 1, failed: 1 },
          pending: 1,
          failed: 1,
          stuck: 2,
          needs_attention: true,
          onboarded: true,
          gateway_configured: true,
        })
      ),
      http.get(DOCS, () =>
        HttpResponse.json({
          items: [
            { id: 3, invoice_number: 'INV-3', icv: 3, status: 'failed', created_at: '2026-06-03T10:00:00Z' },
            { id: 2, invoice_number: 'INV-2', icv: 2, status: 'pending', created_at: '2026-06-03T09:00:00Z' },
            { id: 1, invoice_number: 'INV-1', icv: 1, status: 'signed', created_at: '2026-06-03T08:00:00Z' },
          ],
          total: 3,
        })
      )
    );

    renderPage();

    expect(
      await screen.findByText('1 pending and 1 failed document(s) need attention.')
    ).toBeInTheDocument();
    expect(screen.getByText('Reconcile now')).toBeInTheDocument();
    expect(screen.queryByText('No fiscal documents yet')).not.toBeInTheDocument();
  });
});
