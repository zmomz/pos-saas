import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import QuotationManagement from './QuotationManagement';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the quotations list.
//
// Each quotation row's destructive delete control rendered a bare <Trash2/>
// glyph inside a <Button> with no visible text and no aria-label: a screen
// reader announced it only as "button", indistinguishable from the adjacent
// "View document" / "Convert to sale" actions — WCAG 4.1.2 (name, role,
// value). This slice gives it a stable accessible name that also carries the
// quote number, so the target row is unambiguous when a list is scanned.

const BASE = 'http://127.0.0.1:8000/api/v1';
const LIST_URL = `${BASE}/entities/quotations`;

function listHandler() {
  return http.get(LIST_URL, () =>
    HttpResponse.json({
      items: [
        { id: 5, quote_number: 'Q-0005', customer_name: 'Acme', total_amount: 115, status: 'draft' },
      ],
    })
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <QuotationManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem('pos_auth_token', 'tok-123');
});

describe('QuotationManagement delete button a11y (#226)', () => {
  it('names the icon-only delete button after its quote number', async () => {
    server.use(listHandler());
    renderPage();

    // Announced as "Delete Q-0005", not a nameless "button".
    const del = await screen.findByRole('button', { name: /delete.*Q-0005/i });
    expect(del).toBeInTheDocument();
  });
});
