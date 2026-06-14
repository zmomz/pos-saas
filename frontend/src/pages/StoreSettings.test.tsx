import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import StoreSettings from './StoreSettings';

// ISSUE-079 — the merchant store-settings screen loads the store identity +
// operating defaults from the server on mount and PUTs them on save. These feed
// every receipt/invoice (seller name + VAT are written through to the client row).

const BASE = 'http://127.0.0.1:8000/api/v1';
const URL = `${BASE}/store-settings`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ThemeProvider>
          <StoreSettings />
        </ThemeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('StoreSettings server persistence', () => {
  it('loads the persisted store settings from the server on mount', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({
          store_name: 'Falafel House',
          vat_number: '300000000000003',
          cr_number: '1010101010',
          receipt_footer: 'Thanks for visiting',
          address: 'King Fahd Rd',
          city: 'Riyadh',
          phone: '+966500000000',
          business_hours: null,
        })
      )
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByDisplayValue('Falafel House')).toBeInTheDocument()
    );
    expect(screen.getByDisplayValue('300000000000003')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1010101010')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Riyadh')).toBeInTheDocument();
  });

  it('saves the edited settings to the server via PUT', async () => {
    let putBody: any = null;
    server.use(
      http.get(URL, () =>
        HttpResponse.json({
          store_name: '',
          vat_number: '',
          cr_number: '',
          receipt_footer: '',
          address: '',
          city: '',
          phone: '',
          business_hours: null,
        })
      ),
      http.put(URL, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json(putBody);
      })
    );

    renderPage();
    // Wait for the load to settle (empty form ready).
    const crInput = await screen.findByPlaceholderText(/Commercial Registration/i);

    const user = userEvent.setup();
    await user.type(crInput, '7007007007');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody.cr_number).toBe('7007007007');
    // The per-day business hours go up with the save so they persist.
    expect(Array.isArray(putBody.business_hours)).toBe(true);
  });
});
