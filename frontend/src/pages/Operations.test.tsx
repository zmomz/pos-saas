import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Operations from './Operations';

// Issue #209 (parity #10/#13): the ops console surfaces health/api-usage/metrics
// telemetry, gracefully marks the platform-admin-only metrics panel when it 403s
// for a merchant, and runs the on-demand ZATCA integrity check + global search.

const BASE = 'http://127.0.0.1:8000/api/v1';
const HEALTH = `${BASE}/production/health/detailed`;
const USAGE = `${BASE}/production/api-usage/stats`;
const METRICS = `${BASE}/production/metrics`;
const SEARCH = `${BASE}/production/search`;
const INTEGRITY = `${BASE}/zatca/integrity`;

function healthHandler(status: 'healthy' | 'degraded' = 'healthy') {
  return http.get(HEALTH, () =>
    HttpResponse.json({
      status,
      checks: {
        database: status === 'healthy' ? 'healthy' : 'unhealthy: connection refused',
        rate_limiter: 'healthy',
        performance_monitor: 'healthy',
        timestamp: '2026-06-29T10:00:00Z',
      },
    })
  );
}

function usageHandler() {
  return http.get(USAGE, () =>
    HttpResponse.json({
      user_id: 'u1',
      total_requests: 1234,
      endpoints: [{ endpoint: '/api/v1/pos/transaction', request_count: 800, avg_response_time_ms: 42.5 }],
      rate_limit: { remaining_tokens: 90, max_tokens: 100, refill_rate_per_second: 10 },
    })
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Operations />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Operations (#209)', () => {
  it('renders system health, KPIs, and per-endpoint usage from the telemetry endpoints', async () => {
    server.use(healthHandler('healthy'), usageHandler(), http.get(METRICS, () =>
      HttpResponse.json({
        summary: { total_requests: 50, total_errors: 1, error_rate: 2.0, avg_response_ms: 30, endpoints_tracked: 1 },
        endpoints: { '/api/v1/pos/transaction': { avg_ms: 30, min_ms: 5, max_ms: 120, p95_ms: 90, total_requests: 50, error_count: 1 } },
        rate_limiter: { remaining_tokens: 90 },
      })
    ));

    renderPage();

    expect(await screen.findByText('All systems operational')).toBeInTheDocument();
    expect(screen.getAllByText('Total requests').length).toBeGreaterThan(0);
    expect(screen.getByText('1,234')).toBeInTheDocument();
    // per-endpoint usage table renders the metered endpoint
    expect(screen.getAllByText('/api/v1/pos/transaction').length).toBeGreaterThan(0);
  });

  it('shows the admin-only note instead of an error when /metrics 403s for a merchant', async () => {
    server.use(
      healthHandler('healthy'),
      usageHandler(),
      http.get(METRICS, () => new HttpResponse(null, { status: 403 }))
    );

    renderPage();

    expect(
      await screen.findByText('Server performance metrics are available to platform administrators.')
    ).toBeInTheDocument();
    // the rest of the console still renders — not a page-level error
    expect(screen.getByText('All systems operational')).toBeInTheDocument();
  });

  it('surfaces a degraded health check distinctly', async () => {
    server.use(
      healthHandler('degraded'),
      usageHandler(),
      http.get(METRICS, () => new HttpResponse(null, { status: 403 }))
    );

    renderPage();

    expect(await screen.findByText('Service degraded')).toBeInTheDocument();
  });

  it('runs the ZATCA integrity check and displays the verified result', async () => {
    server.use(
      healthHandler('healthy'),
      usageHandler(),
      http.get(METRICS, () => new HttpResponse(null, { status: 403 })),
      http.get(INTEGRITY, () =>
        HttpResponse.json({ ok: true, total: 7, chain_ok: true, signatures_ok: true, broken_at: null, detail: null })
      )
    );

    renderPage();

    const btn = await screen.findByRole('button', { name: 'Run integrity check' });
    await userEvent.click(btn);

    expect(await screen.findByText('Chain verified — 7 document(s) intact.')).toBeInTheDocument();
  });

  it('runs a global search and lists matched products', async () => {
    server.use(
      healthHandler('healthy'),
      usageHandler(),
      http.get(METRICS, () => new HttpResponse(null, { status: 403 })),
      http.get(SEARCH, () =>
        HttpResponse.json({
          query: 'latte',
          total_results: 1,
          results: {
            products: [{ id: 1, name: 'Latte', name_ar: null, barcode: '123', price: 18, category: 'Drinks' }],
            customers: [],
            transactions: [],
          },
        })
      )
    );

    renderPage();

    await screen.findByText('All systems operational');
    const input = screen.getByPlaceholderText('Search products, customers, invoices…');
    await userEvent.type(input, 'latte');
    await userEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('Latte')).toBeInTheDocument();
    expect(screen.getByText('1 result(s)')).toBeInTheDocument();
  });

  it('shows a page-level error only when every telemetry panel fails', async () => {
    server.use(
      http.get(HEALTH, () => new HttpResponse(null, { status: 500 })),
      http.get(USAGE, () => new HttpResponse(null, { status: 500 })),
      http.get(METRICS, () => new HttpResponse(null, { status: 500 }))
    );

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText('Could not load operations telemetry. Please try again.')
      ).toBeInTheDocument();
    });
  });
});
