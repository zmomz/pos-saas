import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Operations from './Operations';

// #273 (Productivity follow-up — global-search deep-linking): a ⌘K transaction
// hit deep-links to /ops?q=<invoice>. Landing there must seed the ops search box
// AND auto-run the query — the user came here to see that record, not to retype it.

const BASE = 'http://127.0.0.1:8000/api/v1';
const HEALTH = `${BASE}/production/health/detailed`;
const USAGE = `${BASE}/production/api-usage/stats`;
const METRICS = `${BASE}/production/metrics`;
const SEARCH = `${BASE}/production/search`;

function telemetry() {
  return [
    http.get(HEALTH, () =>
      HttpResponse.json({ status: 'healthy', checks: { database: 'healthy', timestamp: 't' } }),
    ),
    http.get(USAGE, () =>
      HttpResponse.json({ user_id: 'u1', total_requests: 0, endpoints: [], rate_limit: { remaining_tokens: 1, max_tokens: 1, refill_rate_per_second: 1 } }),
    ),
    http.get(METRICS, () => new HttpResponse(null, { status: 403 })),
  ];
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LanguageProvider>
        <Operations />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Operations deep-link (#273)', () => {
  it('seeds the search box from ?q= and auto-runs the query', async () => {
    let receivedQ: string | null = null;
    server.use(
      ...telemetry(),
      http.get(SEARCH, ({ request }) => {
        receivedQ = new URL(request.url).searchParams.get('q');
        return HttpResponse.json({
          query: 'INV-9',
          total_results: 1,
          results: {
            products: [],
            customers: [],
            transactions: [{ id: 9, invoice_number: 'INV-9', total_amount: 50 }],
          },
        });
      }),
    );

    renderAt('/ops?q=INV-9');

    // The hit renders with no user interaction — the deep-link ran the search.
    expect(await screen.findByText('INV-9')).toBeInTheDocument();
    expect(receivedQ).toBe('INV-9');

    const input = screen.getByPlaceholderText(/search products/i) as HTMLInputElement;
    expect(input.value).toBe('INV-9');
  });

  it('does not auto-search when there is no ?q=', async () => {
    let called = false;
    server.use(
      ...telemetry(),
      http.get(SEARCH, () => {
        called = true;
        return HttpResponse.json({ query: '', total_results: 0, results: { products: [], customers: [], transactions: [] } });
      }),
    );

    renderAt('/ops');

    await screen.findByText('All systems operational');
    expect(called).toBe(false);
  });
});
