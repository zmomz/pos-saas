import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import CustomerManagement from './CustomerManagement';

// ISSUE-208 (M11 FE-Platform) — the customers list must speak the one shared
// table voice: the `.dxr-tbl` primitive (<DataTable>), not a bespoke hand-rolled
// `<table className="w-full text-sm">`. Column semantics (name, contact, tags,
// consent, actions) must survive the migration.

const BASE = 'http://127.0.0.1:8000';

const ONE_CUSTOMER = {
  items: [
    {
      id: 'c1',
      name: 'Layla Hassan',
      phone: '+966500000001',
      email: 'layla@example.com',
      vat_number: '300000000000003',
      marketing_consent: true,
      tags: ['vip', 'wholesale'],
      pii_erased_at: null,
    },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <CustomerManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('CustomerManagement shared table voice (ISSUE-208)', () => {
  it('renders the customers list through the shared .dxr-tbl primitive', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(ONE_CUSTOMER))
    );

    const { container } = renderPage();

    // The row's name proves the list rendered.
    expect(await screen.findByText('Layla Hassan')).toBeInTheDocument();

    // One shared table voice: the DataTable renders <table class="dxr-tbl">,
    // and there must be no bespoke hand-rolled table left behind.
    expect(container.querySelector('table.dxr-tbl')).toBeInTheDocument();
    expect(container.querySelector('table.text-sm')).not.toBeInTheDocument();
  });

  it('preserves the contact, tag and consent cells after the migration', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/customers`, () => HttpResponse.json(ONE_CUSTOMER))
    );

    const { container } = renderPage();

    expect(await screen.findByText('Layla Hassan')).toBeInTheDocument();
    // Contact columns survive.
    expect(screen.getByText('+966500000001')).toBeInTheDocument();
    expect(screen.getByText('layla@example.com')).toBeInTheDocument();
    // Both segmentation tags render inside the table row (not just the filter chips).
    const table = container.querySelector('table.dxr-tbl') as HTMLElement;
    expect(within(table).getByText('vip')).toBeInTheDocument();
    expect(within(table).getByText('wholesale')).toBeInTheDocument();
    // Marketing-consent state survives (opted-in pill).
    expect(within(table).getByText(/opted in/i)).toBeInTheDocument();
  });
});
