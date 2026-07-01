import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// ISSUE-208 (M11 FE-Platform) — adopt the shared states/primitives everywhere.
// ReportsAnalytics was the last source page still hand-rolling loading
// placeholders as bespoke `bg-muted animate-pulse` blocks. Every loading
// placeholder must now come from the shared `<Skeleton>` primitive, which
// carries a stable `data-slot="skeleton"` marker so the design system can
// recognise it as one voice.

const BASE = 'http://127.0.0.1:8000';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ReportsAnalytics />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Keep every report panel in its loading state by never resolving its fetch, so
// all skeleton placeholders are on screen at once.
function stubPending() {
  server.use(http.get(`${BASE}/api/v1/*`, () => new Promise(() => {})));
}

describe('ReportsAnalytics loading skeletons (ISSUE-208)', () => {
  it('renders loading placeholders through the shared Skeleton primitive', () => {
    stubPending();
    const { container } = renderPage();

    // On first paint every panel is loading, so shared skeletons are present.
    const skeletons = container.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('leaves no bespoke pulse placeholder that is not a shared Skeleton', () => {
    stubPending();
    const { container } = renderPage();

    // No `animate-pulse` element may exist that isn't a shared Skeleton.
    const pulses = Array.from(container.querySelectorAll('.animate-pulse'));
    const bespoke = pulses.filter((el) => el.getAttribute('data-slot') !== 'skeleton');
    expect(bespoke).toHaveLength(0);
  });
});
