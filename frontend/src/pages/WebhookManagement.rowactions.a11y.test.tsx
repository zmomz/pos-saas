import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import WebhookManagement from './WebhookManagement';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the webhooks list.
//
// Two icon-only controls on each webhook row were nameless to a screen reader:
//   - the destructive delete <Button> (bare <Trash2/>), and
//   - the copy-secret <button> (bare <Copy/> glyph).
// Both announced only as "button" — WCAG 4.1.2 (name, role, value). This slice
// gives the delete button a name carrying the webhook it targets and labels the
// copy-secret button, so neither is an unlabelled mystery control.

const BASE = 'http://127.0.0.1:8000/api/v1';
const WEBHOOKS_URL = `${BASE}/entities/webhooks`;

const WEBHOOK = {
  id: 'wh-1',
  name: 'Orders sync',
  url: 'https://example.com/hook',
  events: ['order.created'],
  secret_key: 'whsec_abcdef123456',
  is_active: true,
};

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

describe('WebhookManagement row-action a11y (#226)', () => {
  it('names the icon-only delete button after the webhook it targets', async () => {
    server.use(http.get(WEBHOOKS_URL, () => HttpResponse.json({ items: [WEBHOOK] })));
    renderPage();

    const del = await screen.findByRole('button', { name: /delete.*orders sync/i });
    expect(del).toBeInTheDocument();
  });

  it('names the icon-only copy-secret button', async () => {
    server.use(http.get(WEBHOOKS_URL, () => HttpResponse.json({ items: [WEBHOOK] })));
    renderPage();

    await screen.findByText('Orders sync');
    const copy = screen.getByRole('button', { name: /copy/i });
    expect(copy).toBeInTheDocument();
  });
});
