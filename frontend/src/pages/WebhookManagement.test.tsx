import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import WebhookManagement from './WebhookManagement';

// ISSUE-020 (H24 / U5.1): the Delivery Logs tab fetched a non-existent endpoint
// (/production/webhooks/logs) and swallowed the 404, so the tab rendered "No
// delivery logs" forever — a missing feature looked identical to an empty log.
// These tests pin:
//   1. a failing logs fetch surfaces a real error state in the logs tab;
//   2. a healthy (empty) logs response still shows the empty view (no false error).

const BASE = 'http://127.0.0.1:8000/api/v1';
const WEBHOOKS_URL = `${BASE}/entities/webhooks`;
const LOGS_URL = `${BASE}/production/webhooks/logs`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <WebhookManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('WebhookManagement surfaces a delivery-logs load error instead of a silent empty tab (ISSUE-020 / H24)', () => {
  it('shows an error state in the logs tab — not "No delivery logs" — when the logs fetch 404s', async () => {
    server.use(
      http.get(WEBHOOKS_URL, () => HttpResponse.json({ items: [] })),
      http.get(LOGS_URL, () => new HttpResponse(null, { status: 404 }))
    );

    renderPage();

    fireEvent.click(await screen.findByText('Delivery Logs'));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('No delivery logs')).not.toBeInTheDocument();
  });

  it('shows the empty logs view — not an error — when the logs endpoint is healthy but empty', async () => {
    server.use(
      http.get(WEBHOOKS_URL, () => HttpResponse.json({ items: [] })),
      http.get(LOGS_URL, () => HttpResponse.json({ items: [] }))
    );

    renderPage();

    fireEvent.click(await screen.findByText('Delivery Logs'));

    expect(await screen.findByText('No delivery logs')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
