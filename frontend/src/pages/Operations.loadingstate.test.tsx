import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Operations from './Operations';

// #208 (M11 FE-Platform) — states adoption. The page-level loading guard uses
// the shared `LoadingState` (aria-live status region) instead of a bespoke
// `animate-pulse` text block.

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Operations />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Operations loading state adoption (#208)', () => {
  it('renders the shared LoadingState (status region), not a bespoke animate-pulse block', () => {
    const { container } = renderPage();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });
});
