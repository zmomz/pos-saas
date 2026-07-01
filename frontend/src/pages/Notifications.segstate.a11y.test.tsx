import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The composer's Channel selector (Email/WhatsApp/Push)
// signalled its selected segment with `data-active` (styling) ALONE — no
// `aria-pressed`, so a screen-reader user got no cue which channel was active
// (WCAG 1.4.1 / 4.1.2).

const LIST_URL = 'http://127.0.0.1:8000/api/v1/notifications/list';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Notifications />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notifications channel segmented-control a11y (#226)', () => {
  it('announces the active channel via aria-pressed', async () => {
    server.use(http.get(LIST_URL, () => HttpResponse.json({ items: [], unread_count: 0 })));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /compose/i }));

    // 'email' is the default channel, so it must announce as pressed.
    expect(
      await screen.findByRole('button', { name: 'Email', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'WhatsApp', pressed: false })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Push', pressed: false })
    ).toBeInTheDocument();
  });
});
