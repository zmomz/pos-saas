import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import PackageManagement from './PackageManagement';

// Issue #236 (A3): deactivating (archiving) a package that still has agents on it
// must warn with the affected-agents count/consequence before it runs, so the
// master sees the blast radius. Read-only preview via /packages/{id}/impact.

const BASE = 'http://127.0.0.1:8000';
const LIST = `${BASE}/api/v1/packages/list`;

function pkg(over = {}) {
  return {
    id: 3, name: 'Pro', client_slots: 5, wholesale_price: 100,
    suggested_retail_price: 150, is_active: true, features: [], ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <PackageManagement />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PackageManagement deactivate blast-radius (#236 A3)', () => {
  it('warns with the affected-agents count when deactivating an in-use package', async () => {
    server.use(
      http.get(LIST, () => HttpResponse.json({ items: [pkg()], total: 1 })),
      http.get(`${BASE}/api/v1/packages/3/impact`, () =>
        HttpResponse.json({ package_id: 3, agent_count: 4, active_agent_count: 4 })
      ),
    );
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /deactivate/i }));

    const impact = await screen.findByTestId('pkg-deactivate-impact');
    expect(impact).toHaveTextContent('4');
    expect(impact).toHaveTextContent(/agent/i);
  });

  it('does not show the affected-agents warning when no agents are on the package', async () => {
    server.use(
      http.get(LIST, () => HttpResponse.json({ items: [pkg()], total: 1 })),
      http.get(`${BASE}/api/v1/packages/3/impact`, () =>
        HttpResponse.json({ package_id: 3, agent_count: 0, active_agent_count: 0 })
      ),
    );
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /deactivate/i }));

    // The confirm still appears (yes/no), but with no affected-agents count.
    await screen.findByRole('button', { name: /yes/i });
    await waitFor(() =>
      expect(screen.queryByTestId('pkg-deactivate-impact')).not.toBeInTheDocument()
    );
  });
});
