import { describe, it, expect, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';
import { DataPagination } from './DataPagination';

// ISSUE-244 — DataPagination hardcoded English "of"/"Previous"/"Next" appear on
// every paginated list; an ar/hi/ur user saw English connectors. These must
// localize through t().

function renderAt(lang: string) {
  localStorage.setItem('pos-language', lang);
  return render(
    <LanguageProvider>
      <DataPagination page={1} pageSize={10} total={42} onPageChange={() => {}} />
    </LanguageProvider>
  );
}

afterEach(() => localStorage.removeItem('pos-language'));

describe('DataPagination i18n (ISSUE-244)', () => {
  it('renders the range connector localized in Arabic (not the English word "of")', () => {
    renderAt('ar');
    // Range row reads "1–10 <of> 42"; the connector must be Arabic, not "of".
    expect(screen.getByText(/42/)).toBeInTheDocument();
    expect(screen.queryByText(/\bof\b/)).toBeNull();
    expect(screen.getByText(/من/)).toBeInTheDocument();
  });

  it('localizes Previous/Next button labels in Arabic', () => {
    renderAt('ar');
    expect(screen.queryByText('Previous')).toBeNull();
    expect(screen.queryByText('Next')).toBeNull();
    expect(screen.getByText('السابق')).toBeInTheDocument();
    expect(screen.getByText('التالي')).toBeInTheDocument();
  });

  it('still renders English connectors in English', () => {
    renderAt('en');
    expect(screen.getByText(/of/)).toBeInTheDocument();
    expect(screen.getByText('Previous')).toBeInTheDocument();
    expect(screen.getByText('Next')).toBeInTheDocument();
  });
});
