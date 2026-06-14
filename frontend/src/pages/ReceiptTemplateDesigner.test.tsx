import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReceiptTemplateDesigner from './ReceiptTemplateDesigner';

// ISSUE-048 (H26) — a merchant edits the receipt-template knobs the ESC/POS
// renderer honors (#45) and sees a live preview reflecting the edits. Saving
// persists the template that drives actual printed output.

const BASE = 'http://127.0.0.1:8000';
const TEMPLATES = `${BASE}/api/v1/entities/receipt_templates`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ReceiptTemplateDesigner />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ReceiptTemplateDesigner', () => {
  it('loads the default template into the editor and preview', async () => {
    server.use(
      http.get(TEMPLATES, () =>
        HttpResponse.json({
          items: [
            {
              id: 5,
              name: 'Main',
              header_text: 'Welcome to Falafel House',
              footer_text: 'See you soon',
              show_logo: true,
              show_qr_code: true,
              paper_size: '80mm',
              font_size: 'medium',
              is_default: true,
            },
          ],
          total: 1,
          skip: 0,
          limit: 20,
        }),
      ),
    );

    renderPage();

    // The header field is populated from the saved default template...
    const header = await screen.findByLabelText(/header text/i);
    expect(header).toHaveValue('Welcome to Falafel House');

    // ...and the live preview reflects it.
    const preview = screen.getByTestId('receipt-preview');
    expect(within(preview).getByText('Welcome to Falafel House')).toBeInTheDocument();
    expect(within(preview).getByText('See you soon')).toBeInTheDocument();
  });

  it('updates the live preview as fields change', async () => {
    server.use(http.get(TEMPLATES, () => HttpResponse.json({ items: [], total: 0 })));

    renderPage();

    const footer = await screen.findByLabelText(/footer text/i);
    await userEvent.clear(footer);
    await userEvent.type(footer, 'Thanks for visiting');

    const preview = screen.getByTestId('receipt-preview');
    expect(within(preview).getByText('Thanks for visiting')).toBeInTheDocument();
  });

  it('hides the QR placeholder in the preview when show_qr_code is off', async () => {
    server.use(
      http.get(TEMPLATES, () =>
        HttpResponse.json({
          items: [{ id: 1, name: 'Main', show_qr_code: true, is_default: true }],
          total: 1,
        }),
      ),
    );

    renderPage();

    await screen.findByLabelText(/header text/i);
    const preview = screen.getByTestId('receipt-preview');
    expect(within(preview).getByTestId('preview-qr')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/show qr code/i));
    expect(within(preview).queryByTestId('preview-qr')).not.toBeInTheDocument();
  });

  it('saves edits to the existing default template via PUT', async () => {
    let putBody: Record<string, unknown> | null = null;
    server.use(
      http.get(TEMPLATES, () =>
        HttpResponse.json({
          items: [{ id: 7, name: 'Main', footer_text: 'old', is_default: true }],
          total: 1,
        }),
      ),
      http.put(`${TEMPLATES}/7`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 7, ...putBody });
      }),
    );

    renderPage();

    const footer = await screen.findByLabelText(/footer text/i);
    await userEvent.clear(footer);
    await userEvent.type(footer, 'new footer');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.footer_text).toBe('new footer');
    expect(putBody!.is_default).toBe(true);
  });

  it('creates a default template via POST when none exists yet', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.get(TEMPLATES, () => HttpResponse.json({ items: [], total: 0 })),
      http.post(TEMPLATES, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 11, ...posted });
      }),
    );

    renderPage();

    const header = await screen.findByLabelText(/header text/i);
    await userEvent.type(header, 'My Store');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.header_text).toBe('My Store');
    expect(posted!.is_default).toBe(true);
    expect(posted!.name).toBeTruthy();
  });
});
