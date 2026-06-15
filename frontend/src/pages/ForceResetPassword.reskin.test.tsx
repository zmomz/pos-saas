import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-093 — re-skin + i18n/RTL for the auth gate first-login reset screen.
// All chrome must route through t() in the selected language and the page must
// flip direction with the language, mirroring the established pattern.

const authState = {
  user: { role: 'agent', name: 'Sam' } as { role: string; name?: string },
  refetch: vi.fn(),
  logout: vi.fn(),
};

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

vi.mock('@/lib/api', () => ({
  changePassword: vi.fn(),
  getClientProfile: vi.fn(),
  setBusinessType: vi.fn(),
}));

import ForceResetPassword from './ForceResetPassword';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ForceResetPassword />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('ForceResetPassword re-skin (i18n/RTL)', () => {
  it('renders the reset form in English with LTR direction', () => {
    localStorage.setItem('pos-language', 'en');

    const { container } = renderPage();

    expect(screen.getByText('Set a new password')).toBeInTheDocument();
    expect(container.querySelector('[dir="ltr"]')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', () => {
    localStorage.setItem('pos-language', 'ar');

    const { container } = renderPage();

    expect(screen.getByText('تعيين كلمة مرور جديدة')).toBeInTheDocument();
    // Security prompt is translated chrome (was an inline English fallback).
    // The user's name shares the paragraph as data, so match the chrome substring.
    expect(screen.getByText(/لأسباب أمنية يجب استبدال كلمة المرور المؤقتة قبل المتابعة\./)).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    // No hardcoded English chrome leaking into the Arabic view.
    expect(screen.queryByText('Set a new password')).not.toBeInTheDocument();
  });
});
