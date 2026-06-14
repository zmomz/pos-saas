import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// ISSUE-075 — Reprint past receipts. From the refund/history view a cashier can
// pick a past sale and reprint its receipt. The reprint request must carry the
// `reprint=true` flag so the backend stamps the duplicate + audits it; the
// thermal print itself is best-effort (WebUSB is unavailable under jsdom).

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
  ];
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
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal reprint past receipt (ISSUE-075)', () => {
  it('reprints a selected past sale with the reprint flag set', async () => {
    let reprintFlag: string | null = null;
    server.use(
      http.get(PRODUCTS_URL, () =>
        HttpResponse.json([{ id: 1, name: 'Juice', price: 12, vat_rate: 0.15 }])
      ),
      http.get(`${BASE}/pos/transactions`, () =>
        HttpResponse.json({
          items: [
            {
              id: 7,
              invoice_number: 'INV-0007',
              total_amount: 13.8,
              subtotal: 12,
              vat_amount: 1.8,
              payment_method: 'cash',
              status: 'completed',
              created_at: '2026-06-10T10:00:00Z',
            },
          ],
        })
      ),
      http.get(`${BASE}/pos/transactions/7/escpos`, ({ request }) => {
        reprintFlag = new URL(request.url).searchParams.get('reprint');
        return HttpResponse.json({ invoice_number: 'INV-0007', format: 'escpos', encoding: 'base64', data: 'AQ==' });
      }),
      ...mountSideHandlers()
    );

    const user = userEvent.setup();
    renderPage();

    // Enter the refund/history view, then pick the past sale.
    await user.click(await screen.findByRole('button', { name: /refund/i }));
    await user.click(await screen.findByText('INV-0007'));

    // Reprint it.
    await user.click(await screen.findByRole('button', { name: /reprint/i }));

    await waitFor(() => expect(reprintFlag).toBe('true'));
  });
});
