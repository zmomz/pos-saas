import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import StaffManagement from './StaffManagement';

// ISSUE-035 — the staff-permission editor. An owner opens a staff member's
// permissions and grants/denies a managed key; the choice posts to the
// owner-scoped endpoint that writes the override row taking effect in
// has_permission over the role default.

const BASE = 'http://127.0.0.1:8000';
const STAFF_URL = `${BASE}/api/v1/entities/staff_members`;
const PERMS_URL = `${BASE}/api/v1/production/staff-permissions/5`;

const STAFF = {
  items: [
    { id: 5, user_id: 'owner1', name: 'Mona Manager', email: 'mona@shop.test', role: 'manager', is_active: true },
  ],
  total: 1,
  skip: 0,
  limit: 200,
};

function managerMap() {
  return {
    staff_member_id: 5,
    role: 'manager',
    has_login: true,
    permissions: [
      { permission_key: 'pos.discount', role_default: true, override: null, effective: true },
      { permission_key: 'pos.price_override', role_default: true, override: null, effective: true },
      { permission_key: 'pos.refund', role_default: true, override: null, effective: true },
      { permission_key: 'pos.void', role_default: true, override: null, effective: true },
    ],
  };
}

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
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('StaffManagement permission editor (ISSUE-035)', () => {
  it('denies a managed key and posts the override to the owner-scoped endpoint', async () => {
    let posted: { permission_key?: string; is_granted?: boolean | null } | null = null;
    server.use(
      http.get(STAFF_URL, () => HttpResponse.json(STAFF)),
      http.get(PERMS_URL, () => HttpResponse.json(managerMap())),
      http.post(PERMS_URL, async ({ request }) => {
        posted = (await request.json()) as { permission_key?: string; is_granted?: boolean | null };
        return HttpResponse.json({
          staff_member_id: 5,
          permission_key: posted.permission_key,
          override: posted.is_granted,
          effective: posted.is_granted,
        });
      })
    );

    renderPage();

    // Open the permissions editor for the manager.
    const row = (await screen.findByText('Mona Manager')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: /permissions/i }));

    // The dialog lists the managed keys; deny pos.void.
    const voidRow = (await screen.findByText('pos.void')).closest('[data-perm-row]')!;
    await userEvent.click(within(voidRow as HTMLElement).getByRole('button', { name: /^denied$/i }));

    expect(posted).toEqual({ permission_key: 'pos.void', is_granted: false });
  });
});
