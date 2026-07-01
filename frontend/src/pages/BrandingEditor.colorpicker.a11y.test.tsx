import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BrandingEditor from './BrandingEditor';

// ISSUE-226 (a11y · SR audit) — the two native `<input type="color">` brand
// swatches carried no accessible name: the visible <Label> next to them is not
// associated (no htmlFor), and only the sibling hex text field had an
// aria-label. A screen-reader user tabbing onto the swatch heard an unnamed
// control. Each swatch must announce which brand colour it edits.

const URL = 'http://127.0.0.1:8000/api/v1/tenant/agent/branding';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <BrandingEditor />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('BrandingEditor color swatches — accessible names (ISSUE-226)', () => {
  it('names each native color-picker swatch for screen readers', async () => {
    server.use(http.get(URL, () => HttpResponse.json({})));

    const { container } = renderPage();

    // Wait for the editor (the hex text field is already labelled).
    await screen.findByLabelText('Primary Color');

    // There are exactly two native swatches.
    const swatches = container.querySelectorAll('input[type="color"]');
    expect(swatches).toHaveLength(2);

    // Each is reachable by its accessible name and is the color input itself.
    const primary = screen.getByLabelText('Primary color picker');
    expect(primary).toHaveAttribute('type', 'color');

    const secondary = screen.getByLabelText('Secondary color picker');
    expect(secondary).toHaveAttribute('type', 'color');
  });
});
