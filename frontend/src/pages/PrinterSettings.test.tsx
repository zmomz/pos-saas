import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PrinterSettings from './PrinterSettings';

// ISSUE-047 — a merchant saves/selects a default printer and the selection
// persists; the page is the UI half of the per-station routing feature.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <PrinterSettings />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PrinterSettings', () => {
  it('lists the merchant saved printers', async () => {
    server.use(
      http.get(`${BASE}/api/v1/printers`, () =>
        HttpResponse.json([
          { id: 1, name: 'Front', role: 'receipt', is_default: true, paper_size: '80mm' },
          { id: 2, name: 'Grill', role: 'kot', station_id: 7, is_default: false },
        ])
      )
    );

    renderPage();

    expect(await screen.findByText('Front')).toBeInTheDocument();
    expect(screen.getByText('Grill')).toBeInTheDocument();
  });

  it('saves a new default printer (POST carries role + is_default)', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.get(`${BASE}/api/v1/printers`, () => HttpResponse.json([])),
      http.post(`${BASE}/api/v1/printers`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 9, ...posted });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /add printer/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByPlaceholderText(/printer name/i), 'Counter');
    await userEvent.selectOptions(within(dialog).getByLabelText(/role/i), 'kot');
    await userEvent.click(within(dialog).getByRole('checkbox'));
    await userEvent.click(within(dialog).getByRole('button', { name: /add printer/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.name).toBe('Counter');
    expect(posted!.role).toBe('kot');
    expect(posted!.is_default).toBe(true);
  });

  it('selecting a printer as default sends a PUT', async () => {
    let putBody: Record<string, unknown> | null = null;
    server.use(
      http.get(`${BASE}/api/v1/printers`, () =>
        HttpResponse.json([{ id: 3, name: 'Back', role: 'receipt', is_default: false }])
      ),
      http.put(`${BASE}/api/v1/printers/3`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 3, name: 'Back', role: 'receipt', is_default: true });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /set as default/i }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.is_default).toBe(true);
  });
});
