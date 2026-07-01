import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DiscountManagement from './DiscountManagement';

// ISSUE-208 (M11 FE-Platform) — the discounts list must speak the one shared
// table voice: the `.dxr-tbl` primitive (<DataTable>), not a bespoke hand-rolled
// `<table className="w-full text-sm">`. Column semantics (code, formatted value,
// usage, status) must survive the migration.

const BASE = 'http://127.0.0.1:8000';

const ONE_DISCOUNT = {
  items: [
    {
      id: 'd1',
      code: 'SAVE10',
      type: 'percentage',
      value: 10,
      min_purchase: 50,
      usage_count: 3,
      max_uses: 100,
      is_active: true,
      starts_at: null,
      ends_at: null,
    },
  ],
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DiscountManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DiscountManagement shared table voice (ISSUE-208)', () => {
  it('renders the discounts list through the shared .dxr-tbl primitive', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(ONE_DISCOUNT))
    );

    const { container } = renderPage();

    // The row's code proves the list rendered.
    expect(await screen.findByText('SAVE10')).toBeInTheDocument();

    // One shared table voice: the DataTable renders <table class="dxr-tbl">,
    // and there must be no bespoke hand-rolled table left behind.
    expect(container.querySelector('table.dxr-tbl')).toBeInTheDocument();
    expect(container.querySelector('table.text-sm')).not.toBeInTheDocument();
  });

  it('preserves the percentage-value and usage cells after the migration', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/discounts`, () => HttpResponse.json(ONE_DISCOUNT))
    );

    renderPage();

    // Percentage discounts render "10%"; usage renders "3 / 100".
    expect(await screen.findByText('10%')).toBeInTheDocument();
    expect(screen.getByText(/3\s*\/\s*100/)).toBeInTheDocument();
  });
});
