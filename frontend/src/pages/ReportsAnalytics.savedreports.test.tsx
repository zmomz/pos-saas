import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ReportsAnalytics from './ReportsAnalytics';

// #273 (Productivity follow-up) — "Saved reports": a named, persisted snapshot of
// the report configuration (the period selector). Distinct from list-screen saved
// filters — this captures the Reports page's own config and re-applies it in one
// click, surviving a reload. Reuses the SavedFilterBar + useSavedFilters machinery.

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
beforeEach(() => localStorage.clear());
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());

describe('ReportsAnalytics saved reports (#273)', () => {
  it('saves the current period as a named report and re-applies it in one click', async () => {
    server.use(http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null)));
    const user = userEvent.setup();
    renderPage();

    // Switch the period away from the default (daily) to weekly, then save that view.
    fireEvent.click(await screen.findByRole('button', { name: 'Weekly' }));
    expect(screen.getByRole('button', { name: 'Weekly', pressed: true })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Name this report…'), 'Weekly snapshot');
    await user.click(screen.getByRole('button', { name: 'Save report' }));

    // Reset back to daily — the saved chip must survive and restore weekly.
    fireEvent.click(screen.getByRole('button', { name: 'Daily' }));
    expect(screen.getByRole('button', { name: 'Daily', pressed: true })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Apply saved report Weekly snapshot' }));
    expect(screen.getByRole('button', { name: 'Weekly', pressed: true })).toBeInTheDocument();
  });

  it('persists saved reports across a remount', async () => {
    server.use(http.get(`${BASE}/api/v1/*`, () => HttpResponse.json(null)));
    const user = userEvent.setup();
    const { unmount } = renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Monthly' }));
    await user.type(screen.getByPlaceholderText('Name this report…'), 'Monthly close');
    await user.click(screen.getByRole('button', { name: 'Save report' }));
    unmount();

    renderPage();
    const chip = await screen.findByRole('button', { name: 'Apply saved report Monthly close' });
    expect(chip).toBeInTheDocument();

    // Re-applying after a fresh mount restores the monthly period.
    fireEvent.click(chip);
    expect(screen.getByRole('button', { name: 'Monthly', pressed: true })).toBeInTheDocument();
    // And a remove control is offered for the preset.
    expect(
      within(chip.parentElement as HTMLElement).getByRole('button', {
        name: 'Remove saved report Monthly close',
      }),
    ).toBeInTheDocument();
  });
});
