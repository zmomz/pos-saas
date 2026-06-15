import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-093 — re-skin + i18n/RTL for the auth gate login screen (Index).
// All chrome must route through t() in the selected language and the page must
// flip direction with the language, mirroring the established pattern
// (CustomerManagement / SupplierManagement).

const authState = {
  user: null as { role: string } | null,
  loading: false,
  login: vi.fn(),
  register: vi.fn(),
};

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

import Index from './Index';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Index />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  authState.user = null;
  authState.loading = false;
});

describe('Index (login) re-skin (i18n/RTL)', () => {
  it('renders the login form in English with LTR direction', () => {
    localStorage.setItem('pos-language', 'en');

    const { container } = renderPage();

    expect(screen.getByText('Welcome to POS System')).toBeInTheDocument();
    // Direction follows the language (was absent before).
    expect(container.querySelector('[dir="ltr"]')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic, including the register toggle', () => {
    localStorage.setItem('pos-language', 'ar');

    const { container } = renderPage();

    expect(screen.getByText('مرحباً بكم في نظام نقاط البيع')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    // The register-toggle chrome must be translated (was hardcoded English).
    expect(screen.getByText('ليس لديك حساب؟ سجّل')).toBeInTheDocument();
    // No hardcoded English toggle copy leaking into the Arabic view.
    expect(screen.queryByText(/Don't have an account/i)).not.toBeInTheDocument();
  });

  it('switches to register mode with translated chrome (Arabic)', () => {
    localStorage.setItem('pos-language', 'ar');

    renderPage();

    fireEvent.click(screen.getByText('ليس لديك حساب؟ سجّل'));

    // Register submit button + the inverse toggle render translated.
    expect(screen.getByText('إنشاء حساب')).toBeInTheDocument();
    expect(screen.getByText('لديك حساب بالفعل؟ تسجيل الدخول')).toBeInTheDocument();
  });
});
