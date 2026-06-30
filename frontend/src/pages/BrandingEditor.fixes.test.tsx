import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import BrandingEditor from './BrandingEditor';

// ISSUE-233 — BrandingEditor truthfulness fixes: invalid hex must be unsaveable,
// the live preview's button text must mirror the runtime contrast guard
// (readableTextColor) so preview == runtime, and toasts must be localized.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const URL = 'http://127.0.0.1:8000/api/v1/tenant/agent/branding';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <BrandingEditor />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
  localStorage.clear();
});
afterAll(() => server.close());

describe('BrandingEditor hex validation (B2)', () => {
  it('blocks the save and shows a localized error when the hex is invalid', async () => {
    let putCount = 0;
    server.use(
      http.get(URL, () => HttpResponse.json({})),
      http.put('http://127.0.0.1:8000/api/v1/branding/update', () => {
        putCount += 1;
        return HttpResponse.json({});
      }),
    );

    renderPage();
    await screen.findByText('Live Preview');

    const hex = screen.getByLabelText('Primary Color');
    await userEvent.clear(hex);
    await userEvent.type(hex, 'zzz');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Enter a valid hex color, e.g. #1488A6.'),
    );
    expect(putCount).toBe(0);
  });

  it('normalizes a valid hex (missing #) before saving and confirms with a localized success toast', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(URL, () => HttpResponse.json({})),
      http.put('http://127.0.0.1:8000/api/v1/branding/update', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({});
      }),
    );

    renderPage();
    await screen.findByText('Live Preview');

    const hex = screen.getByLabelText('Primary Color');
    await userEvent.clear(hex);
    await userEvent.type(hex, '1488A6');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body!.primary_color).toBe('#1488a6');
    expect(toast.success).toHaveBeenCalledWith('Branding saved');
  });
});

describe('BrandingEditor preview contrast (B3)', () => {
  it('flips preview button text to dark ink on a pale brand and warns', async () => {
    server.use(http.get(URL, () => HttpResponse.json({})));

    renderPage();
    await screen.findByText('Live Preview');

    const hex = screen.getByLabelText('Primary Color');
    await userEvent.clear(hex);
    await userEvent.type(hex, '#ffffff');

    // The runtime contrast guard returns near-black ink (#0a0a0a) for a pale
    // brand; the preview's solid-brand button must use the same colour.
    const previewBtn = screen.getByRole('button', { name: 'Primary Button' });
    await waitFor(() => expect(previewBtn).toHaveStyle({ color: 'rgb(10, 10, 10)' }));

    // The merchant is warned that white-on-brand can't be used as-is.
    expect(
      screen.getByText('This color is pale — text switches to dark for readability.'),
    ).toBeInTheDocument();
  });
});

describe('BrandingEditor localized toasts (B4)', () => {
  it('surfaces a localized failure toast in Arabic when the save 500s', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(
      http.get(URL, () => HttpResponse.json({})),
      http.put('http://127.0.0.1:8000/api/v1/branding/update', () => new HttpResponse(null, { status: 500 })),
    );

    renderPage();
    await screen.findByText('معاينة مباشرة');

    await userEvent.click(screen.getByRole('button', { name: 'حفظ' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'تعذّر حفظ العلامة التجارية. يرجى المحاولة مرة أخرى.',
      ),
    );
  });
});
