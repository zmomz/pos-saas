import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ForecastInsights from './ForecastInsights';

// #228 (M9·AI): the frontend surface for the AI forecasting epic. It fetches the
// three read-only /reports/* forecast endpoints (sales-forecast,
// inventory-forecast, dynamic-pricing) and turns them into three operator-facing
// panels: a sales-revenue projection, a smart-reorder list, and a dynamic-pricing
// list. This test drives that behaviour through the rendered component.

const BASE = 'http://127.0.0.1:8000';

const SALES = {
  method: 'moving_average',
  lookback_days: 30,
  horizon_days: 7,
  history_total: 21000,
  avg_daily_sales: 700,
  points: [
    { date: '2026-07-02', forecast_sales: 700 },
    { date: '2026-07-03', forecast_sales: 700 },
  ],
};

const INVENTORY = {
  method: 'velocity',
  lookback_days: 30,
  horizon_days: 14,
  total: 1,
  items: [
    {
      product_id: 1,
      name: 'Widget',
      name_ar: null,
      on_hand: 10,
      avg_daily_units: 5,
      projected_demand: 70,
      days_of_cover: 2,
      will_stock_out: true,
      suggested_reorder_quantity: 60,
    },
  ],
};

const PRICING = {
  method: 'demand_elasticity_proxy',
  lookback_days: 30,
  low_cover_days: 7,
  high_cover_days: 60,
  total: 1,
  items: [
    {
      product_id: 2,
      name: 'Gadget',
      name_ar: null,
      on_hand: 4,
      avg_daily_units: 8,
      days_of_cover: 0.5,
      signal: 'markup',
      current_price: 20,
      suggested_price: 22,
      adjustment_pct: 10,
    },
  ],
};

function stub({
  sales = SALES,
  inventory = INVENTORY,
  pricing = PRICING,
}: { sales?: unknown; inventory?: unknown; pricing?: unknown } = {}) {
  server.use(
    http.get(`${BASE}/api/v1/reports/sales-forecast`, () =>
      sales === 'error' ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(sales)
    ),
    http.get(`${BASE}/api/v1/reports/inventory-forecast`, () =>
      inventory === 'error' ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(inventory)
    ),
    http.get(`${BASE}/api/v1/reports/dynamic-pricing`, () =>
      pricing === 'error' ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(pricing)
    )
  );
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

describe('ForecastInsights (#228 AI forecasting surface)', () => {
  it('projects sales revenue from the moving-average baseline', async () => {
    stub();
    renderPanel();
    // The average-daily-sales baseline that is projected forward is surfaced.
    expect(await screen.findByText('Avg Daily Sales')).toBeInTheDocument();
    expect(screen.getByText(/700/)).toBeInTheDocument();
  });

  it('lists a will-stock-out product with its suggested reorder quantity', async () => {
    stub();
    renderPanel();
    const widget = await screen.findByText('Widget');
    const row = widget.closest('tr') as HTMLElement;
    // The smart-reorder shortfall quantity (60) is the actionable output.
    expect(within(row).getByText('60')).toBeInTheDocument();
  });

  it('lists a scarce product with its markup current→suggested price', async () => {
    stub();
    renderPanel();
    const gadget = await screen.findByText('Gadget');
    const row = gadget.closest('tr') as HTMLElement;
    expect(within(row).getByText(/22/)).toBeInTheDocument(); // suggested price
    expect(within(row).getByText('Markup')).toBeInTheDocument(); // signal
  });

  it('flags a markdown that was floored at cost so it never sells below cost', async () => {
    stub({
      pricing: {
        ...PRICING,
        items: [
          {
            product_id: 3,
            name: 'ThinMargin',
            name_ar: null,
            on_hand: 1000,
            avg_daily_units: 0.1,
            days_of_cover: 10000,
            signal: 'markdown',
            current_price: 50,
            suggested_price: 45,
            adjustment_pct: -10,
            cost_price: 45,
            margin_floored: true,
          },
        ],
      },
    });
    renderPanel();
    const row = (await screen.findByText('ThinMargin')).closest('tr') as HTMLElement;
    expect(within(row).getByText(/45/)).toBeInTheDocument(); // suggested = cost floor
    expect(within(row).getByText('At cost')).toBeInTheDocument(); // margin-floor badge
  });

  it('shows an empty state when nothing needs reordering or repricing', async () => {
    stub({
      inventory: { ...INVENTORY, total: 0, items: [] },
      pricing: { ...PRICING, total: 0, items: [] },
    });
    renderPanel();
    expect(await screen.findByText('All products are well-stocked.')).toBeInTheDocument();
    expect(screen.getByText('No price changes suggested.')).toBeInTheDocument();
  });

  it('surfaces a load error distinct from an empty forecast', async () => {
    stub({ sales: 'error' });
    renderPanel();
    // The failing sales panel shows the shared retry error, not a zero forecast.
    expect(await screen.findByText('Could not load data. Please retry.')).toBeInTheDocument();
  });
});
