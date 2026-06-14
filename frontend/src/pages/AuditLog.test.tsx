import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AuditLog from './AuditLog';

// ISSUE-027 (H5) — the backend now returns a resolved `user_email` and a
// normalized `action` verb (create/update/delete/sale/export/auth_failure/other)
// instead of a bare `user_id` and a verbose `METHOD /path`. The page must render
// the email in the User column and colour the action badge by verb.

const BASE = 'http://127.0.0.1:8000';

const AUDIT = {
  items: [
    { id: '1', user_email: 'cashier@shop.test', action: 'create', details: 'status=201' },
    { id: '2', user_email: 'manager@shop.test', action: 'delete', details: 'status=200' },
    { id: '3', user_email: 'intruder@evil.test', action: 'auth_failure', details: 'status=401' },
  ],
  total: 3,
  skip: 0,
  limit: 200,
};

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

describe('AuditLog renders against real fields (ISSUE-027)', () => {
  it('shows the resolved actor email in the User column', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json(AUDIT))
    );
    renderPage();

    const table = await screen.findByRole('table');
    expect(within(table).getByText('cashier@shop.test')).toBeInTheDocument();
    expect(within(table).getByText('manager@shop.test')).toBeInTheDocument();
    expect(within(table).getByText('intruder@evil.test')).toBeInTheDocument();
  });

  it('colours the action badge by normalized verb', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json(AUDIT))
    );
    renderPage();

    const table = await screen.findByRole('table');
    expect(within(table).getByText('Create')).toHaveClass('text-green-400');
    expect(within(table).getByText('Delete')).toHaveClass('text-red-400');
    // Failed-auth attempts are a recognized, security-relevant verb (red badge).
    expect(within(table).getByText('Auth Failure')).toHaveClass('text-red-400');
  });
});
