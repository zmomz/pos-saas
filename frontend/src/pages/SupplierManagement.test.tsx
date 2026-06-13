import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SupplierManagement from './SupplierManagement';

// ISSUE-063 — suppliers capture/store/display a VAT (TRN) number. The list shows
// each supplier's VAT number, and the Add form captures it on create.

const BASE = 'http://127.0.0.1:8000';

const ONE_SUPPLIER = {
  items: [
    {
      id: '1',
      name: 'Acme Foods',
      contact_person: 'Sara',
      email: 'sara@acme.test',
      phone: '+966500000000',
      payment_terms: 'Net 30',
      vat_number: '300000000000003',
      status: 'active',
    },
  ],
  total: 1,
};

const EMPTY = { items: [], total: 0 };

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SupplierManagement VAT number (ISSUE-063)', () => {
  it("displays a supplier's VAT number in the list", async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(ONE_SUPPLIER)),
      http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY))
    );

    renderPage();

    expect(await screen.findByText('300000000000003')).toBeInTheDocument();
  });

  it('captures the VAT number when adding a supplier', async () => {
    let createdVat: string | undefined;
    server.use(
      http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(EMPTY)),
      http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
      http.post(`${BASE}/api/v1/entities/suppliers`, async ({ request }) => {
        const body = (await request.json()) as { vat_number?: string };
        createdVat = body.vat_number;
        return HttpResponse.json({ id: '2', name: 'New Co', vat_number: body.vat_number }, { status: 201 });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /add supplier/i }));
    await userEvent.type(await screen.findByPlaceholderText(/company name/i), 'New Co');
    await userEvent.type(screen.getByPlaceholderText(/300000000000003/), '300000000000003');
    // The dialog's submit button.
    await userEvent.click(screen.getByRole('button', { name: /^add supplier$/i }));

    await waitFor(() => expect(createdVat).toBe('300000000000003'));
  });
});
