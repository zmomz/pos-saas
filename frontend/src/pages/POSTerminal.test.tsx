import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
