import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DevicesSettings from './DevicesSettings';

// ISSUE-049 — a merchant registers in-store SoftPOS terminals and sees the list.
// The integrated-terminal backend (/payments/terminals) is the data half; this
// page is the merchant-facing UI half (owner-scoped, brand tokens, i18n/RTL).

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DevicesSettings />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DevicesSettings', () => {
  it('lists the merchant registered terminals', async () => {
    server.use(
      http.get(`${BASE}/api/v1/payments/terminals`, () =>
        HttpResponse.json([
          { id: 1, provider: 'geidea', label: 'Front lane', serial: 'GEI-001', status: 'active' },
          { id: 2, provider: 'geidea', label: 'Drive-thru', serial: 'GEI-002', status: 'active' },
        ])
      )
    );

    renderPage();

    expect(await screen.findByText('Front lane')).toBeInTheDocument();
    expect(screen.getByText('Drive-thru')).toBeInTheDocument();
  });

  it('registers a new terminal then shows it in the list', async () => {
    let posted: Record<string, unknown> | null = null;
    const terminals: Array<Record<string, unknown>> = [];
    server.use(
      http.get(`${BASE}/api/v1/payments/terminals`, () => HttpResponse.json(terminals)),
      http.post(`${BASE}/api/v1/payments/terminals`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        const created = { id: 9, provider: 'geidea', status: 'active', ...posted };
        terminals.push(created);
        return HttpResponse.json(created, { status: 201 });
      })
    );

    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /add terminal/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByPlaceholderText(/terminal name/i), 'Counter 1');
    await userEvent.type(within(dialog).getByPlaceholderText(/serial/i), 'GEI-009');
    await userEvent.click(within(dialog).getByRole('button', { name: /add terminal/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.label).toBe('Counter 1');
    expect(posted!.serial).toBe('GEI-009');

    // the registered terminal appears in the refreshed list
    expect(await screen.findByText('Counter 1')).toBeInTheDocument();
  });
});
