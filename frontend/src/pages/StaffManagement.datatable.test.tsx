import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import StaffManagement from './StaffManagement';

// ISSUE-208 (M11 FE-Platform) — the staff list must speak the one shared table
// voice: the `.dxr-tbl` primitive (<DataTable>), not a bespoke hand-rolled
// `<table className="w-full text-sm">`. Column semantics (name, email, phone,
// role, status, actions) must survive the migration.

const BASE = 'http://127.0.0.1:8000';
const STAFF_URL = `${BASE}/api/v1/entities/staff_members`;

const ONE_STAFF = {
  items: [
    {
      id: 5,
      name: 'Mona Manager',
      email: 'mona@shop.test',
      phone: '+966500000005',
      role: 'manager',
      is_active: true,
    },
  ],
  total: 1,
  skip: 0,
  limit: 200,
};

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

describe('StaffManagement shared table voice (ISSUE-208)', () => {
  it('renders the staff list through the shared .dxr-tbl primitive', async () => {
    server.use(http.get(STAFF_URL, () => HttpResponse.json(ONE_STAFF)));

    const { container } = renderPage();

    expect(await screen.findByText('Mona Manager')).toBeInTheDocument();

    // One shared table voice: the DataTable renders <table class="dxr-tbl">,
    // and there must be no bespoke hand-rolled table left behind.
    expect(container.querySelector('table.dxr-tbl')).toBeInTheDocument();
    expect(container.querySelector('table.text-sm')).not.toBeInTheDocument();
  });

  it('preserves the contact, role and status cells after the migration', async () => {
    server.use(http.get(STAFF_URL, () => HttpResponse.json(ONE_STAFF)));

    const { container } = renderPage();

    expect(await screen.findByText('Mona Manager')).toBeInTheDocument();
    const table = container.querySelector('table.dxr-tbl') as HTMLElement;

    // Contact columns survive.
    expect(within(table).getByText('mona@shop.test')).toBeInTheDocument();
    expect(within(table).getByText('+966500000005')).toBeInTheDocument();
    // Role pill survives.
    expect(table.querySelector('.pill-muted')).toBeInTheDocument();
    // Row actions survive.
    expect(within(table).getByRole('button', { name: /edit/i })).toBeInTheDocument();
  });
});
