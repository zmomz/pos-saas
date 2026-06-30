import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// #199 — self-service forgot-password request screen. The response copy must be
// neutral (anti-enumeration): the same confirmation shows whether or not the
// email maps to a real account, and chrome must i18n/RTL like the auth gate.

const requestPasswordReset = vi.fn();
vi.mock('@/lib/api', () => ({
  requestPasswordReset: (email: string) => requestPasswordReset(email),
}));

import ForgotPassword from './ForgotPassword';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/auth/password/forgot']}>
      <LanguageProvider>
        <ForgotPassword />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('ForgotPassword (request screen)', () => {
  it('renders the request form in English with LTR direction', () => {
    localStorage.setItem('pos-language', 'en');
    const { container } = renderPage();

    expect(screen.getByText('Reset your password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeInTheDocument();
    expect(container.querySelector('[dir="ltr"]')).toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', () => {
    localStorage.setItem('pos-language', 'ar');
    const { container } = renderPage();

    expect(screen.getByText('إعادة تعيين كلمة المرور')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
    expect(screen.queryByText('Reset your password')).not.toBeInTheDocument();
  });

  it('shows the same neutral confirmation for a real account', async () => {
    localStorage.setItem('pos-language', 'en');
    requestPasswordReset.mockResolvedValueOnce({ success: true, message: 'ok', reset_token: null });
    renderPage();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'real@shop.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    await waitFor(() => expect(screen.getByText('Check your email')).toBeInTheDocument());
    // Neutral copy — never asserts the account exists.
    expect(screen.getByText(/If an account matches that email/)).toBeInTheDocument();
  });

  it('shows the identical confirmation for an unknown email (no enumeration)', async () => {
    localStorage.setItem('pos-language', 'en');
    // Backend always 200s; unknown email simply has no dev token.
    requestPasswordReset.mockResolvedValueOnce({ success: true, message: 'ok', reset_token: null });
    renderPage();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'nobody@nowhere.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    await waitFor(() => expect(screen.getByText('Check your email')).toBeInTheDocument());
    expect(screen.getByText(/If an account matches that email/)).toBeInTheDocument();
    // No reveal that the address is unregistered.
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no account/i)).not.toBeInTheDocument();
  });

  it('surfaces a dev-mode shortcut into the reset screen when a token is returned', async () => {
    localStorage.setItem('pos-language', 'en');
    requestPasswordReset.mockResolvedValueOnce({ success: true, message: 'ok', reset_token: 'tok-123' });
    renderPage();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'dev@shop.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    const link = await screen.findByRole('link', { name: 'Continue to reset' });
    expect(link).toHaveAttribute('href', '/auth/password/reset?token=tok-123');
  });
});
