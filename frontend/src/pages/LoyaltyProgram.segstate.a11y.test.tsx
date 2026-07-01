import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import LoyaltyProgram from './LoyaltyProgram';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The Balances/History tabs signalled their selected segment
// with `data-active` (styling) ALONE — no `aria-pressed`, so a screen-reader
// user got no cue which tab was active (WCAG 1.4.1 use-of-colour / 4.1.2). Each
// segment now reflects its selected state into `aria-pressed`.

const BASE = 'http://127.0.0.1:8000/api/v1';

function happyHandlers() {
  return [
    http.get(`${BASE}/production/loyalty/config`, () =>
      HttpResponse.json({ points_per_sar: 1, redemption_rate: 0.1, min_points_redeem: 100, is_active: true })
    ),
    http.get(`${BASE}/production/loyalty/balances`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/production/loyalty/transactions`, () => HttpResponse.json({ items: [] })),
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

describe('LoyaltyProgram segmented-tab a11y (#226)', () => {
  it('announces the active Balances/History tab via aria-pressed', async () => {
    server.use(...happyHandlers());
    renderPage();

    // Default tab is Balances → pressed; History → not pressed.
    expect(
      await screen.findByRole('button', { name: 'Customer Balances', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Points History', pressed: false })
    ).toBeInTheDocument();
  });
});
