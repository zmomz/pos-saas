import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import StoreSettings from './StoreSettings';

// ISSUE-226 (M11 FE-Platform · a11y) — the store-settings screen renders a
// *visible* <Label> above each identity/branch field, but the Labels were never
// programmatically associated with their <Input> (no htmlFor/id). A sighted user
// reads "VAT Number" above the box, but a screen-reader user tabbing into the
// field heard only "edit text" — a placeholder is not a robust accessible name
// (it vanishes on type and dom-accessibility-api does not count it). The receipt
// footer had no <Label> at all. WCAG 1.3.1 (info & relationships) / 3.3.2
// (labels or instructions). Every field must expose its accessible name so
// getByLabelText can reach it.

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

describe('StoreSettings form field labelling (ISSUE-226 a11y)', () => {
  const LABELLED_FIELDS = [
    'Store name',
    'VAT Number',
    'Commercial Registration (CR) number',
    'Receipt footer',
    'Address',
    'City',
    'Phone',
  ];

  it('exposes each store-settings field by its visible label as accessible name', async () => {
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
      )
    );

    renderPage();
    // Wait for the load to settle (the form is present from first render).
    await waitFor(() => expect(screen.getByText('Store name')).toBeInTheDocument());

    for (const field of LABELLED_FIELDS) {
      // Exact-string match (not regex) so parenthesised labels like
      // "Commercial Registration (CR) number" are treated literally.
      const input = screen.getByLabelText(field, { exact: true });
      expect(input.tagName).toBe('INPUT');
    }
  });

  it('gives the business-type selector an accessible name', async () => {
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
      )
    );

    renderPage();
    await waitFor(() => expect(screen.getByText('Store name')).toBeInTheDocument());

    const combo = screen.getByRole('combobox', { name: /choose your business type/i });
    expect(combo).toBeInTheDocument();
  });
});
