import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { formatTime } from '@/lib/format';
import ShiftManagement from './ShiftManagement';

// Issue #208 (M11 FE-Platform) — the open-shift "started" field rendered its
// time via a bespoke `new Date(...).toLocaleTimeString('en-GB', {...})`, bypassing
// the single locale-aware date/time path. It must route through the shared
// `formatTime(value, lang)` helper so times share one Gregorian, Western-numeral,
// locale-aware path across languages (matching formatDate used for history rows).

const BASE = 'http://127.0.0.1:8000/api/v1/production';
const OPENED_AT = '2026-06-03T14:30:00Z';
const OPEN_SHIFT = {
  status: 'open',
  shift: { id: 1, status: 'open', opening_cash: 100, start_time: OPENED_AT },
};
const NO_HISTORY = { shifts: [], total: 0 };

function renderPage() {
  return render(
    <LanguageProvider>
      <ShiftManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());

describe('ShiftManagement started-time formatting (#208)', () => {
  it('renders the open-shift start time via the shared formatTime path (Arabic locale)', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(
      http.get(`${BASE}/shifts/current`, () => HttpResponse.json(OPEN_SHIFT)),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(NO_HISTORY)),
      http.get(`${BASE}/shifts/movements`, () => HttpResponse.json({ movements: [] }))
    );

    renderPage();

    // The bespoke `toLocaleTimeString('en-GB', …)` path ignores the language;
    // the shared helper renders the ar-SA locale form. Asserting the helper's
    // Arabic output pins the render to formatTime, not the hardcoded 'en-GB'.
    expect(await screen.findByText(formatTime(OPENED_AT, 'ar'))).toBeInTheDocument();
  });
});
