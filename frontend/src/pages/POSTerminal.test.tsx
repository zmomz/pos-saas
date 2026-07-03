import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// F-015 (UX-02 / IB §5.E): the POS terminal previously swallowed a products-fetch
// failure into console.error and fell through to the "No products available"
// empty view — an outage looked identical to an empty catalog. These tests pin:
//   1. a products-fetch rejection renders a real error state (not the empty state);
//   2. an empty catalog still renders the empty state (no false error);
//   3. an offline POS shows a persistent connectivity indicator.
// (1) fails before the fix (the empty state shows on a 500, no alert).

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

// The other endpoints POSTerminal fires on mount — kept happy so MSW's
// onUnhandledRequest:'error' guard doesn't trip on unrelated requests.
function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    // HW-05 (F-047): the POS resolves the merchant brand name for the customer
    // display header on mount.
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
  ];
}

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { value, configurable: true });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  setOnline(true);
});
afterAll(() => server.close());

describe('POSTerminal surfaces a products-load error distinct from empty (F-015 / UX-02)', () => {
  it('shows an error state — not the empty state — when the products fetch 500s', async () => {
    server.use(
      http.get(PRODUCTS_URL, () => new HttpResponse(null, { status: 500 })),
      ...mountSideHandlers()
    );

    renderPage();

    // The shared ErrorState carries role="alert".
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('No products available')).not.toBeInTheDocument();
  });

  it('shows the empty state — not an error — when the catalog is genuinely empty', async () => {
    server.use(
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      ...mountSideHandlers()
    );

    renderPage();

    expect(await screen.findByText('No products available')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a persistent offline indicator when the network is down', async () => {
    setOnline(false);
    server.use(
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      ...mountSideHandlers()
    );

    renderPage();

    // The in-chrome offline badge announces the loss of connectivity.
    expect(await screen.findByText('Offline')).toBeInTheDocument();
  });
});

// ISSUE-102 (U3.4): the refund panel rendered amounts with a `$` (USD) symbol on
// a SAR-only product. Refund amounts must read in SAR like the rest of the POS.
describe('POSTerminal refund panel renders amounts in SAR, not USD (ISSUE-102)', () => {
  function refundHandlers() {
    return [
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      // Master grants every permission, including pos.refund.
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ is_master: true, denied: [], granted: [] })
      ),
      http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
      http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
      http.get(`${BASE}/tenant/client/branding`, () =>
        HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
      ),
      http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
      http.get(`${BASE}/pos/transactions`, () =>
        HttpResponse.json([
          {
            id: 1,
            invoice_number: 'INV-001',
            total_amount: 100,
            payment_method: 'cash',
            items: [{ product_id: 1, name: 'Widget', price: 50, quantity: 2 }],
          },
        ])
      ),
    ];
  }

  it('shows the refund amount in SAR with no USD symbol once a sale is selected', async () => {
    server.use(...refundHandlers());

    renderPage();

    // Enter refund mode, then pick the recent sale to open the refund detail panel.
    fireEvent.click(await screen.findByRole('button', { name: 'Refund' }));
    fireEvent.click(await screen.findByText('INV-001'));

    // The refund amount (and the line/list amounts) read in SAR…
    // (formatMoney renders "<number> ⃁" with the Saudi Riyal sign for the en locale).
    expect(await screen.findByText('Refund Amount')).toBeInTheDocument();
    expect(screen.getAllByText(/[\d,]+\.\d{2}\s*⃁/).length).toBeGreaterThan(0);

    // …and the USD symbol is gone from the refund path.
    expect(screen.queryByText(/\$\s*[\d,]/)).not.toBeInTheDocument();
  });
});

describe('POSTerminal refund receipt shows the real Subtotal/VAT breakdown (ISSUE-5)', () => {
  // Regression: the refund success receipt hard-coded subtotal: 0 / vat_amount: 0
  // while the Total was correct, so the credit-note receipt rendered 0.00 for the
  // Subtotal and VAT lines. The backend now returns the credit note's stored
  // (negative) subtotal + vat_amount on the refund response, and the receipt reads
  // them straight through. This pins that all three lines are consistent.
  function refundHandlers() {
    return [
      http.get(PRODUCTS_URL, () => HttpResponse.json([])),
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ is_master: true, denied: [], granted: [] })
      ),
      http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
      http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
      http.get(`${BASE}/tenant/client/branding`, () =>
        HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
      ),
      http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
      http.get(`${BASE}/pos/transactions`, () =>
        HttpResponse.json([
          {
            id: 1,
            invoice_number: 'INV-001',
            total_amount: 14.37,
            payment_method: 'cash',
            items: [{ product_id: 1, name: 'Widget', price: 12.5, quantity: 1 }],
          },
        ])
      ),
      // The credit note carries negative subtotal/VAT/total (mirrors the backend).
      http.post(`${BASE}/pos/transactions/1/refund`, () =>
        HttpResponse.json({
          credit_note_id: 2,
          original_transaction_id: 1,
          credit_note_number: 'CRN-0001-000001',
          total_amount: -14.37,
          subtotal: -12.5,
          vat_amount: -1.87,
          zatca_status: 'disabled',
          original_status: 'refunded',
        })
      ),
    ];
  }

  it('renders non-zero Subtotal and VAT on the credit-note receipt', async () => {
    server.use(...refundHandlers());

    renderPage();

    // Enter refund mode, pick the sale (defaults every line to a full return), then
    // process the refund to open the credit-note receipt.
    fireEvent.click(await screen.findByRole('button', { name: 'Refund' }));
    fireEvent.click(await screen.findByText('INV-001'));
    fireEvent.click(await screen.findByRole('button', { name: /Process Refund/ }));

    // The receipt shows the credit note number once it has processed.
    expect(await screen.findByText(/CRN-0001-000001/)).toBeInTheDocument();

    // The Subtotal and VAT lines carry the stored (negative) values — NOT 0.00.
    // formatMoneyAr renders "<western-digits> ﷼"; the receipt uses the Riyal sign.
    // (-12.50 also appears as the returned line amount, hence getAllByText.)
    expect(screen.getAllByText(/-12\.50/).length).toBeGreaterThan(0);
    expect(screen.getByText(/-1\.87/)).toBeInTheDocument();
    expect(screen.getByText(/-14\.37/)).toBeInTheDocument();
    // The pre-fix bug rendered the Subtotal + VAT lines as a plain "0.00" — guard
    // against that specific regression coming back.
    expect(screen.queryByText(/^\s*0\.00\s*﷼?\s*$/)).not.toBeInTheDocument();
  });
});
