import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import FloorMap from './FloorMap';

// ISSUE-226 (a11y) — screen-reader pass on the floor map. The zone-filter
// segmented control marked the selected zone with a visual `data-active`
// attribute only; a screen-reader user could not tell which zone filter was
// active. Each segment now exposes its selected state via `aria-pressed`
// (SegButton primitive).

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  server.use(
    http.get(`${BASE}/api/v1/restaurant/zones`, () =>
      HttpResponse.json([{ id: 1, name: 'Patio' }]),
    ),
    http.get(`${BASE}/api/v1/restaurant/tables`, () => HttpResponse.json({ items: [], total: 0 })),
  );
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <FloorMap />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FloorMap zone-filter a11y (ISSUE-226)', () => {
  it('announces the active zone-filter tab via aria-pressed', async () => {
    renderPage();
    // "All zones" is selected by default; the "Patio" zone tab is not.
    const allZones = await screen.findByRole('button', { name: /all zones/i });
    expect(allZones).toHaveAttribute('aria-pressed', 'true');
    const patio = screen.getByRole('button', { name: 'Patio' });
    expect(patio).toHaveAttribute('aria-pressed', 'false');
  });
});
