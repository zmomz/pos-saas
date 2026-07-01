import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PeakHoursHeatmap from './PeakHoursHeatmap';

// #229 (M9·Analytics): the frontend surface for the peak-hours heatmap. It reads
// the tenant-scoped /reports/peak-hours endpoint (completed sales bucketed into a
// day-of-week × hour grid) and renders a heatmap plus a "busiest time" callout.

const BASE = 'http://127.0.0.1:8000';

// A Monday (dow=1) 09:00 cell with 3 orders is the hottest; a Wednesday (dow=3)
// 14:00 cell with 1 order is quieter.
const HEATMAP = {
  method: 'sales_heatmap',
  lookback_days: 365,
  total_orders: 4,
  total_revenue: 65,
  busiest: { day_of_week: 1, hour: 9, order_count: 3, revenue: 60 },
  cells: [
    { day_of_week: 1, hour: 9, order_count: 3, revenue: 60 },
    { day_of_week: 3, hour: 14, order_count: 1, revenue: 5 },
  ],
};

function stub(body: unknown = HEATMAP) {
  server.use(
    http.get(`${BASE}/api/v1/reports/peak-hours`, () =>
      body === 'error' ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(body)
    )
  );
}

function renderPanel() {
  return render(
    <LanguageProvider>
      <PeakHoursHeatmap />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PeakHoursHeatmap (#229 analytics surface)', () => {
  it('calls out the busiest time (weekday + hour + order count)', async () => {
    stub();
    renderPanel();
    // The hottest cell is Monday 09:00 with 3 orders.
    const busiest = await screen.findByTestId('busiest-time');
    expect(busiest).toHaveTextContent('Mon');
    expect(busiest).toHaveTextContent('09');
    expect(busiest).toHaveTextContent('3');
  });

  it('renders an active cell reachable by its accessible name', async () => {
    stub();
    renderPanel();
    // Each non-empty bucket exposes an accessible name naming day, hour and count.
    const cell = await screen.findByLabelText(/Mon.*09.*3/);
    expect(cell).toBeInTheDocument();
  });

  it('shows an empty state when there are no sales', async () => {
    stub({ ...HEATMAP, total_orders: 0, busiest: null, cells: [] });
    renderPanel();
    expect(await screen.findByText('Nothing here yet')).toBeInTheDocument();
  });

  it('surfaces a load error distinct from an empty heatmap', async () => {
    stub('error');
    renderPanel();
    expect(await screen.findByText('Could not load data. Please retry.')).toBeInTheDocument();
  });
});
