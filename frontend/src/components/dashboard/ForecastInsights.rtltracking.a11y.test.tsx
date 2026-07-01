import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ForecastInsights from './ForecastInsights';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset, extended to the
// ForecastInsights stat labels. The sales-forecast card surfaces its three
// numeric stats (Avg Daily Sales / Projected Demand / Daily Trend) under a
// classic Latin `uppercase tracking-wide` overline treatment. Arabic joins its
// letters cursively, so that tracking shatters the joins under an Arabic/RTL
// locale; the base `[dir='rtl']` reset in index.css lives in @layer base and
// loses to Tailwind's utility layer. This mirrors the `rtl:tracking-normal`
// idiom already applied to the sidebar nav-section and ⌘K group overlines.

const BASE = 'http://127.0.0.1:8000';

// linear_trend surfaces all three uppercase stat labels (the Daily Trend one is
// gated on this method), so a single render exercises every overline.
const SALES = {
  method: 'linear_trend',
  lookback_days: 30,
  horizon_days: 7,
  history_total: 21000,
  avg_daily_sales: 700,
  trend_per_day: 5,
  points: [{ date: '2026-07-02', forecast_sales: 700 }],
};
const INVENTORY = { method: 'velocity', lookback_days: 30, horizon_days: 14, total: 0, items: [] };
const PRICING = {
  method: 'demand_elasticity_proxy',
  lookback_days: 30,
  low_cover_days: 7,
  high_cover_days: 60,
  total: 0,
  items: [],
};

function stub() {
  server.use(
    http.get(`${BASE}/api/v1/reports/sales-forecast`, () => HttpResponse.json(SALES)),
    http.get(`${BASE}/api/v1/reports/inventory-forecast`, () => HttpResponse.json(INVENTORY)),
    http.get(`${BASE}/api/v1/reports/dynamic-pricing`, () => HttpResponse.json(PRICING))
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ForecastInsights stat-label RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on every uppercase stat overline label under RTL', async () => {
    stub();
    const { container } = render(
      <LanguageProvider>
        <ForecastInsights />
      </LanguageProvider>
    );
    // Wait for the three stat labels to render.
    await screen.findByText('Daily Trend');
    const overlines = container.querySelectorAll('p.uppercase.tracking-wide');
    expect(overlines.length).toBe(3);
    overlines.forEach((label) => {
      expect(label.className).toContain('rtl:tracking-normal');
    });
  });
});
