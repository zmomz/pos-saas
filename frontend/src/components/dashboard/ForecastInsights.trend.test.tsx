import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ForecastInsights from './ForecastInsights';

// #228 (M9·AI): the sales-forecast endpoint exposes two self-describing models on
// one route, selected with ?method= — the flat `moving_average` (default) and the
// direction-aware `linear_trend`. This test drives the ForecastInsights method
// toggle that lets an operator switch between them and read the day-over-day
// trend the linear model projects.

const BASE = 'http://127.0.0.1:8000';

const MOVING = {
  method: 'moving_average',
  lookback_days: 30,
  horizon_days: 7,
  history_total: 21000,
  avg_daily_sales: 700,
  trend_per_day: 0,
  points: [{ date: '2026-07-02', forecast_sales: 700 }],
};

const RISING = {
  method: 'linear_trend',
  lookback_days: 30,
  horizon_days: 7,
  history_total: 21000,
  avg_daily_sales: 700,
  trend_per_day: 25,
  points: [{ date: '2026-07-02', forecast_sales: 725 }],
};

const FALLING = { ...RISING, trend_per_day: -25 };

const INVENTORY = { method: 'velocity', lookback_days: 30, horizon_days: 14, total: 0, items: [] };
const PRICING = {
  method: 'demand_elasticity_proxy',
  lookback_days: 30,
  low_cover_days: 7,
  high_cover_days: 60,
  total: 0,
  items: [],
};

// Records every sales-forecast request's ?method= and replies by method.
function stubSalesByMethod(byMethod: Record<string, unknown>) {
  const seen: string[] = [];
  server.use(
    http.get(`${BASE}/api/v1/reports/sales-forecast`, ({ request }) => {
      const method = new URL(request.url).searchParams.get('method') || 'moving_average';
      seen.push(method);
      return HttpResponse.json(byMethod[method] ?? byMethod.moving_average);
    }),
    http.get(`${BASE}/api/v1/reports/inventory-forecast`, () => HttpResponse.json(INVENTORY)),
    http.get(`${BASE}/api/v1/reports/dynamic-pricing`, () => HttpResponse.json(PRICING))
  );
  return seen;
}

function renderPanel() {
  return render(
    <LanguageProvider>
      <ForecastInsights />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ForecastInsights sales-method toggle (#228 linear-trend surface)', () => {
  it('defaults to the moving-average model and requests it on mount', async () => {
    const seen = stubSalesByMethod({ moving_average: MOVING, linear_trend: RISING });
    renderPanel();
    expect(await screen.findByText('Avg Daily Sales')).toBeInTheDocument();
    expect(seen).toContain('moving_average');
  });

  it('re-fetches with method=linear_trend when the Linear Trend model is chosen', async () => {
    const seen = stubSalesByMethod({ moving_average: MOVING, linear_trend: RISING });
    renderPanel();
    await screen.findByText('Avg Daily Sales');

    await userEvent.click(screen.getByRole('button', { name: 'Linear Trend' }));

    await waitFor(() => expect(seen).toContain('linear_trend'));
    // The chosen model is reflected as pressed.
    expect(screen.getByRole('button', { name: 'Linear Trend' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('surfaces a positive daily trend as a Rising direction', async () => {
    stubSalesByMethod({ moving_average: MOVING, linear_trend: RISING });
    renderPanel();
    await screen.findByText('Avg Daily Sales');

    await userEvent.click(screen.getByRole('button', { name: 'Linear Trend' }));

    const trend = await screen.findByTestId('sales-trend');
    expect(within(trend).getByText('Rising')).toBeInTheDocument();
    expect(within(trend).getByText(/25/)).toBeInTheDocument();
  });

  it('surfaces a negative daily trend as a Falling direction', async () => {
    stubSalesByMethod({ moving_average: MOVING, linear_trend: FALLING });
    renderPanel();
    await screen.findByText('Avg Daily Sales');

    await userEvent.click(screen.getByRole('button', { name: 'Linear Trend' }));

    const trend = await screen.findByTestId('sales-trend');
    expect(within(trend).getByText('Falling')).toBeInTheDocument();
  });
});
