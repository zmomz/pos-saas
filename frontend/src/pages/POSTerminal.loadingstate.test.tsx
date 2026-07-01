import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// #208 (M11 FE-Platform) — states adoption. The page-level loading guard uses
// the shared `LoadingState` (aria-live status region) instead of a bespoke
// `animate-pulse` text block.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
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

describe('POSTerminal loading state adoption (#208)', () => {
  it('renders the shared LoadingState (status region), not a bespoke animate-pulse block', () => {
    const { container } = renderPage();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });
});
