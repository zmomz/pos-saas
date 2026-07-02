import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AuditLog from './AuditLog';

// ISSUE-272 (M7·Compliance) — the backend-only regulatory-export endpoint must
// have a frontend surface: a download button that surfaces the chain's
// integrity/verified attestation. Fetched lazily on click so the page mount
// (and its existing tests) are unchanged.

const BASE = 'http://127.0.0.1:8000';

const AUDIT = { items: [], total: 0, skip: 0, limit: 200 };

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AuditLog />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
  // jsdom has no object-URL plumbing; stub it so the download step is inert.
  Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), writable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AuditLog — regulatory export (#272)', () => {
  it('downloads the export and shows the verified integrity attestation', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json(AUDIT)),
      http.get(`${BASE}/api/v1/entities/audit_logs/regulatory-export`, () =>
        HttpResponse.json({
          artifact_type: 'regulatory_audit_export',
          format_version: '1.0',
          generated_at: '2026-07-02T00:00:00Z',
          owner_user_id: '1',
          record_count: 3,
          integrity: { verified: true, checked: 3, broken_id: null, reason: null },
          records: [],
        }),
      ),
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /download export/i }));

    expect(await screen.findByText(/chain verified/i)).toBeInTheDocument();
  });
});
