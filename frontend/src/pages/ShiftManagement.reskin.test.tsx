import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ShiftManagement from './ShiftManagement';

// ISSUE-092 — re-skin + i18n/RTL for ShiftManagement. The shift chrome must go
// through t() in the selected language (no hardcoded English copy), flip
// direction with the language, and add the standard error/permission states a
// failed shift fetch should surface (UX-02) — mirroring the reference pattern.

const BASE = 'http://127.0.0.1:8000/api/v1/production';
const NO_SHIFT = { status: 'no_open_shift', shift: null };
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

describe('ShiftManagement states + i18n/RTL (UX-02)', () => {
  it('shows the permission state — not the error state — when the shift fetch 403s', async () => {
    server.use(
      http.get(`${BASE}/shifts/current`, () => new HttpResponse(null, { status: 403 })),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(NO_HISTORY))
    );

    renderPage();

    expect(await screen.findByText(/access/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the error state — not a blank shift — when the shift fetch fails, and retry re-loads', async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/shifts/current`, () => {
        attempt += 1;
        if (attempt === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json(NO_SHIFT);
      }),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(NO_HISTORY))
    );

    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    expect(await screen.findByText(/No active shift/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(
      http.get(`${BASE}/shifts/current`, () => HttpResponse.json(NO_SHIFT)),
      http.get(`${BASE}/shifts/history`, () => HttpResponse.json(NO_HISTORY))
    );

    const { container } = renderPage();

    // Arabic chrome via t() (not the English "Current Shift").
    expect(await screen.findByText('الوردية الحالية')).toBeInTheDocument();
    expect(screen.queryByText('Current Shift')).not.toBeInTheDocument();
    // RTL is applied for Arabic.
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
  });
});
