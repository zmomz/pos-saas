import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import WebhookManagement from './WebhookManagement';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The Webhooks/Delivery-Logs tabs signalled their selected
// segment with `data-active` (styling) ALONE — no `aria-pressed`, so a
// screen-reader user got no cue which tab was active (WCAG 1.4.1 / 4.1.2).

const BASE = 'http://127.0.0.1:8000/api/v1';

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

describe('WebhookManagement segmented-tab a11y (#226)', () => {
  it('announces the active Webhooks/Delivery-Logs tab via aria-pressed', async () => {
    server.use(http.get(`${BASE}/entities/webhooks`, () => HttpResponse.json({ items: [] })));
    renderPage();

    expect(
      await screen.findByRole('button', { name: 'Webhooks', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Delivery Logs', pressed: false })
    ).toBeInTheDocument();
  });
});
