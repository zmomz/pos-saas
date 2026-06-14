import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import DiscountManagement from './DiscountManagement';

// ISSUE-025 (U3.5 inert binding) — the "Total Uses" summary read `used_count`,
// a field GET /api/v1/entities/discounts never returns (it returns `usage_count`),
// so the figure always rendered as 0 regardless of real redemptions.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <DiscountManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('DiscountManagement Total Uses (ISSUE-025)', () => {
  it('sums the real usage_count across discounts', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/discounts`, () =>
        HttpResponse.json({
          items: [
            { id: '1', code: 'SAVE10', type: 'percentage', value: 10, usage_count: 3 },
            { id: '2', code: 'SAVE20', type: 'percentage', value: 20, usage_count: 4 },
          ],
          total: 2,
        })
      )
    );
    renderPage();

    // The "Total Uses" card value sits next to its label in the same wrapper.
    const label = await screen.findByText('Total Uses');
    const card = label.parentElement!;
    // 3 + 4 = 7, not the always-0 placeholder.
    expect(card.textContent).toContain('7');
  });
});
