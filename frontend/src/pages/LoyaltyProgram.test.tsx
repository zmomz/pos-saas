import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import LoyaltyProgram from './LoyaltyProgram';

// ISSUE-020 (C4 / U3.8): the LoyaltyProgram admin page wrapped its three load
// calls (config / balances / transactions) in swallowing try/catch, so a missing
// or failing endpoint rendered the same empty "No loyalty members yet" view as a
// genuinely empty program — the façade silently "worked". These tests pin:
//   1. a failing load surfaces a real error state (not the silent empty view);
//   2. a healthy load still renders data (no false error).

const BASE = 'http://127.0.0.1:8000/api/v1';
const CONFIG_URL = `${BASE}/production/loyalty/config`;
const BALANCES_URL = `${BASE}/production/loyalty/balances`;
const TX_URL = `${BASE}/production/loyalty/transactions`;

function happyHandlers() {
  return [
    http.get(CONFIG_URL, () =>
      HttpResponse.json({ points_per_sar: 1, redemption_rate: 0.1, min_points_redeem: 100, is_active: true })
    ),
    http.get(BALANCES_URL, () =>
      HttpResponse.json({
        items: [
          {
            id: 'c1',
            customer_name: 'Acme',
            customer_id: 'cust1',
            points_balance: 500,
            total_earned: 800,
            total_redeemed: 300,
          },
        ],
      })
    ),
    http.get(TX_URL, () => HttpResponse.json({ items: [] })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <LoyaltyProgram />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('LoyaltyProgram surfaces a load error instead of a silent empty façade (ISSUE-020 / C4)', () => {
  it('shows an error state — not "No loyalty members yet" — when an endpoint 404s', async () => {
    server.use(
      http.get(CONFIG_URL, () => new HttpResponse(null, { status: 404 })),
      http.get(BALANCES_URL, () => new HttpResponse(null, { status: 404 })),
      http.get(TX_URL, () => new HttpResponse(null, { status: 404 }))
    );

    renderPage();

    // The shared ErrorState carries role="alert".
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('No loyalty members yet')).not.toBeInTheDocument();
  });

  it('renders loyalty data with no error when every endpoint is healthy', async () => {
    server.use(...happyHandlers());

    renderPage();

    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
