import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/contexts/ThemeContext';
import StoreSettings from './StoreSettings';

// ISSUE-226 (M11 FE-Platform · a11y) — RTL directional mirroring. The
// change-business-type confirmation dialog previews the transition as
// `{currentType} → {pendingType}`. The literal RIGHTWARDS-arrow glyph is a
// bidi-neutral character: the browser does NOT mirror it under `[dir="rtl"]`,
// so an Arabic/Urdu reader (who scans right-to-left) sees the arrow point
// *away* from the destination type. The dashboards' idiom for a mirrored
// horizontal arrow is Tailwind's `rtl:-scale-x-100` (accept `rtl:rotate-180`
// too); the two type labels already convey the transition to a screen reader,
// so the glyph itself is decorative and must be `aria-hidden`.

const BASE = 'http://127.0.0.1:8000/api/v1';
const URL = `${BASE}/store-settings`;

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ThemeProvider>
          <StoreSettings />
        </ThemeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

function isMirrored(el: Element | null | undefined): boolean {
  const c = el?.getAttribute('class') ?? '';
  return c.includes('rtl:-scale-x-100') || c.includes('rtl:rotate-180');
}

function stubSettings() {
  server.use(
    http.get(URL, () =>
      HttpResponse.json({
        store_name: '',
        vat_number: '',
        cr_number: '',
        receipt_footer: '',
        address: '',
        city: '',
        phone: '',
        business_hours: null,
      })
    )
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('StoreSettings business-type transition arrow RTL mirroring (ISSUE-226)', () => {
  it('mirrors the current→pending transition arrow and hides it from SRs', async () => {
    stubSettings();
    renderPage();
    await waitFor(() => expect(screen.getByText('Store name')).toBeInTheDocument());

    // Pick a different type to open the confirm dialog where the preview renders.
    await userEvent.click(screen.getByRole('combobox', { name: /choose your business type/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'Restaurant' }));

    const arrow = await screen.findByText('→');
    expect(isMirrored(arrow)).toBe(true);
    expect(arrow.getAttribute('aria-hidden')).toBe('true');
  });
});
