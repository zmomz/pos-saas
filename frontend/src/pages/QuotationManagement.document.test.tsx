import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { toast } from 'sonner';
import QuotationManagement from './QuotationManagement';

// FE-11: openDocument previously used a bare fetch() that bypassed the shared
// axios client (and its 401-refresh interceptor) and never checked resp.ok — a
// failing request wrote the backend's error HTML into a new tab. It now routes
// through getQuotationDocument (the shared client), which rejects on a non-2xx
// status, so a failure surfaces a toast and nothing is written to a new window.
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const BASE = 'http://127.0.0.1:8000/api/v1';
const LIST_URL = `${BASE}/entities/quotations`;
const DOC_URL = `${BASE}/entities/quotations/:id/document`;

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

async function clickView() {
  renderPage();
  const viewBtn = await screen.findByRole('button', { name: /view document/i });
  fireEvent.click(viewBtn);
  return viewBtn;
}

describe('QuotationManagement openDocument (FE-11)', () => {
  it('fetches the document through the shared client and writes it to a new window', async () => {
    let auth: string | null = null;
    server.use(
      listHandler(),
      http.get(DOC_URL, ({ request }) => {
        auth = request.headers.get('authorization');
        return new HttpResponse('<html>عرض سعر</html>', {
          headers: { 'Content-Type': 'text/html' },
        });
      })
    );

    const writes: string[] = [];
    const win = { document: { open: vi.fn(), write: (h: string) => writes.push(h), close: vi.fn() } };
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(win as unknown as Window);

    await clickView();

    await waitFor(() => expect(writes).toContain('<html>عرض سعر</html>'));
    // Proves the shared client attached the bearer token (and would refresh on 401).
    expect(auth).toBe('Bearer tok-123');
    expect(toast.error).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it('surfaces a toast and writes nothing when the document request fails', async () => {
    server.use(
      listHandler(),
      http.get(DOC_URL, () => new HttpResponse('boom', { status: 500 }))
    );

    const openSpy = vi.spyOn(window, 'open');

    await clickView();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Could not open quotation document'));
    // The error HTML is never opened in a new tab.
    expect(openSpy).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });
});
