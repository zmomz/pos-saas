import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ClientDashboard from './ClientDashboard';

// #208 (M11 FE-Platform) — states adoption. The page-level loading guard must
// use the shared `LoadingState` (an aria-live status region) rather than a
// bespoke `animate-pulse` text block, so all in-page states look like one system.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ClientDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});
afterAll(() => server.close());

describe('ClientDashboard loading state adoption (#208)', () => {
  it('renders the shared LoadingState (status region), not a bespoke animate-pulse block', () => {
    const { container } = renderPage();

    // Initial render is in the loading guard before any fetch resolves.
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });
});
