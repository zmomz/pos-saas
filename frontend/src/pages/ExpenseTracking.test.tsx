import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ExpenseTracking from './ExpenseTracking';

// ISSUE-022 (H8) — GET /pos/transactions returns `TransactionListResponse
// { items, total }` where each item carries `total_amount`. The page used to read
// `txData.transactions` and sum `tx.total`, so Revenue and Net Profit/Loss were
// permanently 0. Read `items` and sum `total_amount`.

const BASE = 'http://127.0.0.1:8000';

// An expense dated today so it falls inside the current-month window the page sums.
const TODAY = new Date().toISOString().split('T')[0];

const EXPENSES = {
  items: [{ id: 'e1', category: 'Supplies', amount: 40, expense_date: TODAY }],
  total: 1,
};

const TRANSACTIONS = {
  items: [
    { id: 1, total_amount: 100 },
    { id: 2, total_amount: 50 },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ExpenseTracking />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function mockEndpoints() {
  server.use(
    http.get(`${BASE}/api/v1/entities/expenses`, () => HttpResponse.json(EXPENSES)),
    http.get(`${BASE}/api/v1/pos/transactions`, () => HttpResponse.json(TRANSACTIONS))
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ExpenseTracking revenue/profit (ISSUE-022)', () => {
  it('computes Revenue from `items`/`total_amount`', async () => {
    mockEndpoints();
    renderPage();

    const revenueCard = (await screen.findByText('Revenue (Total)')).closest('.rounded-2xl');
    expect(revenueCard).toHaveTextContent('150.00 SAR');
  });

  it('computes Net Profit/Loss as revenue minus this-month expenses', async () => {
    mockEndpoints();
    renderPage();

    // 150 revenue - 40 expenses = 110.
    const netCard = (await screen.findByText('Net Profit/Loss')).closest('.rounded-2xl');
    expect(netCard).toHaveTextContent('110.00 SAR');
  });
});
