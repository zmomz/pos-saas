import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Reservations from './Reservations';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The Waitlist
// card heading is drawn with the lucide `ListOrdered` glyph: numbered list rows
// whose ordinals sit at the *start* of the reading direction (leftwards in LTR).
// A lucide icon is an inline SVG the browser does NOT mirror under `[dir="rtl"]`,
// so an Arabic/Urdu reader (who scans right-to-left) sees the ordinals stranded
// on the wrong edge. Per Material Design bidirectionality, ordered/bulleted list
// glyphs are mirrored in RTL; the dashboards' idiom is Tailwind's
// `rtl:-scale-x-100` (accept `rtl:rotate-180` too).

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Reservations />
      </LanguageProvider>
    </MemoryRouter>
  );
}

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Reservations waitlist-icon RTL mirroring (ISSUE-226)', () => {
  it('mirrors the ListOrdered waitlist glyph so its ordinals read from the right in RTL', async () => {
    server.use(
      http.get(`${BASE}/api/v1/restaurant/tables`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/api/v1/restaurant/reservations`, () => HttpResponse.json({ items: [], total: 0 })),
      http.get(`${BASE}/api/v1/restaurant/waitlist`, () => HttpResponse.json({ items: [], total: 0 }))
    );

    renderPage();

    // The page title ("Reservations & Waitlist") also matches /waitlist/i, so
    // pin to the Waitlist *card* heading by its exact accessible name.
    const heading = await screen.findByRole('heading', { name: 'Waitlist' });
    expect(isMirrored(heading.querySelector('svg'))).toBe(true);
  });
});
