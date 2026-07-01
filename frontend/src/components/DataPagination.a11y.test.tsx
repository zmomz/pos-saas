import { describe, it, expect, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';
import { DataPagination } from './DataPagination';

// ISSUE-226 (a11y · keyboard/SR pass) — the shared list-pagination control
// rendered as an anonymous <div>. A screen-reader user who tabbed to the
// Previous/Next buttons had no way to know they were inside a pagination region,
// and the visible "2 / 5" position read out as "2 slash 5" with no announcement
// when the page changed. Expose the control as a named `navigation` landmark
// whose current position lives in a politely-announced, human-named status.

function renderPager(page: number, lang = 'en') {
  localStorage.setItem('pos-language', lang);
  return render(
    <LanguageProvider>
      <DataPagination page={page} pageSize={10} total={42} onPageChange={() => {}} />
    </LanguageProvider>,
  );
}

afterEach(() => localStorage.removeItem('pos-language'));

describe('DataPagination a11y landmark (ISSUE-226)', () => {
  it('exposes the control as a named pagination navigation landmark', () => {
    renderPager(2);
    expect(
      screen.getByRole('navigation', { name: /pagination/i }),
    ).toBeInTheDocument();
  });

  it('announces the current page position to SRs via a named polite live region', () => {
    renderPager(2); // ceil(42 / 10) = 5 pages
    const status = screen.getByLabelText('Page 2 of 5');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('localizes the landmark and status names (Arabic)', () => {
    renderPager(2, 'ar');
    // Landmark name and status label localize through t(); no English leaks.
    expect(screen.getByRole('navigation', { name: /الصفحات/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/الصفحة 2 من 5/)).toBeInTheDocument();
  });
});
