import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// #208 (M11 FE-Platform) — states adoption. The Notifications loading guard used
// a bespoke spinner-ring (`border-t-transparent` div) — one of the three ad-hoc
// loading treatments the shared `LoadingState` (aria-live `role="status"` region)
// replaces. While the fetch is in flight the page must render the shared state.

const URL = 'http://127.0.0.1:8000/api/v1/notifications/list';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Notifications />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notifications loading state adoption (#208)', () => {
  it('renders the shared LoadingState (status region), not a bespoke spinner ring', () => {
    // Keep the fetch pending so the loading guard stays on for the assertion.
    server.use(http.get(URL, () => new Promise(() => {})));

    const { container } = renderPage();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(container.querySelector('.border-t-transparent')).not.toBeInTheDocument();
  });
});
