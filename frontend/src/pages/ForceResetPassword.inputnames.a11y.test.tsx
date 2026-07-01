import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-226 (a11y · SR pass) — the forced first-login reset form is a core auth
// flow, yet its three password fields carried a `placeholder` and nothing else.
// A placeholder is NOT an accessible name (WCAG 1.3.1/4.1.2): it disappears once
// the field has a value and screen readers do not reliably announce it as a
// label. This pins an explicit accessible name on each field, reusing the
// existing placeholder strings so the visible text and the SR name agree and
// both localise. Mirrors the placeholder+aria-label idiom already on the POS
// scan/search inputs.

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

describe('ForceResetPassword password-field accessible names (a11y)', () => {
  it('names all three password fields in English', () => {
    localStorage.setItem('pos-language', 'en');
    renderPage();

    // getByLabelText resolves the accessible name; a placeholder alone would
    // NOT satisfy it, so these throwing would signal a missing name.
    expect(screen.getByLabelText('Current (temporary) password')).toBeInTheDocument();
    expect(screen.getByLabelText('New password')).toBeInTheDocument();
    expect(screen.getByLabelText('Confirm new password')).toBeInTheDocument();
  });

  it('localises the accessible names in Arabic with no English leak', () => {
    localStorage.setItem('pos-language', 'ar');
    renderPage();

    expect(screen.getByLabelText('كلمة المرور الحالية (المؤقتة)')).toBeInTheDocument();
    expect(screen.getByLabelText('كلمة المرور الجديدة')).toBeInTheDocument();
    expect(screen.getByLabelText('تأكيد كلمة المرور الجديدة')).toBeInTheDocument();

    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
  });
});
