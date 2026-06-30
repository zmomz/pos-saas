import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ChannelOrders from './ChannelOrders';

// Issue #237 — the omnichannel screen surfaces the stuck-claim crash-recovery sweep's
// health: a healthy badge with the last unattended run, or a flag when claims are stuck.
// A failure of that one call degrades only the health card, never the rest of the page.

const BASE = 'http://127.0.0.1:8000';

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/omnichannel/salla/connection`, () =>
      HttpResponse.json({ connected: false, store_id: null, webhook_secret_set: false })
    ),
    http.get(`${BASE}/api/v1/aggregator/connection`, () =>
      HttpResponse.json({ connected: false, location_id: null, webhook_secret_set: false })
    ),
    http.get(`${BASE}/api/v1/omnichannel/channel-orders`, () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })
    ),
  ];
}

function sweepHandler(
  body: Record<string, unknown> | null,
  status = 200
) {
  return http.get(`${BASE}/api/v1/omnichannel/sweep-status`, () =>
    status === 200 && body
      ? HttpResponse.json(body)
      : HttpResponse.json({ detail: 'boom' }, { status })
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ChannelOrders />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ChannelOrders sweep health (#237)', () => {
  it('shows a healthy badge and the last-run recovered count when no claims are stuck', async () => {
    server.use(
      ...baseHandlers(),
      sweepHandler({
        last_run_at: '2026-06-30T12:00:00+00:00',
        last_reopened: 0,
        stuck_count: 0,
        oldest_stuck_age_seconds: null,
        threshold_seconds: 600,
        healthy: true,
      })
    );
    renderPage();

    const card = await screen.findByTestId('sweep-health');
    expect(card).toHaveTextContent(/healthy/i);
  });

  it('flags stuck claims as un-healthy with the stuck count', async () => {
    server.use(
      ...baseHandlers(),
      sweepHandler({
        last_run_at: '2026-06-30T12:00:00+00:00',
        last_reopened: 0,
        stuck_count: 3,
        oldest_stuck_age_seconds: 4000,
        threshold_seconds: 600,
        healthy: false,
      })
    );
    renderPage();

    const card = await screen.findByTestId('sweep-health');
    expect(card).toHaveTextContent('3');
    expect(card).toHaveTextContent(/stuck|recovering|attention/i);
  });

  it('degrades only the health card when the sweep-status call fails', async () => {
    server.use(...baseHandlers(), sweepHandler(null, 500));
    renderPage();

    // The card renders an honest unavailable marker...
    const card = await screen.findByTestId('sweep-health');
    expect(card).toHaveTextContent('—');
    // ...while the rest of the page is intact (the Salla connection card still renders).
    expect(screen.getAllByText(/salla/i).length).toBeGreaterThan(0);
  });
});
