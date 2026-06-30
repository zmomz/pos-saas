import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// #199 — self-service reset-password screen. Reads the single-use token from the
// emailed link (`?token=…`), enforces the local match/length guard, and surfaces
// the backend's complexity/expiry message verbatim.

const resetPassword = vi.fn();
vi.mock('@/lib/api', () => ({
  resetPassword: (token: string, pw: string) => resetPassword(token, pw),
}));

import ResetPassword from './ResetPassword';

function renderPage(initialPath = '/auth/password/reset?token=abc123') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <LanguageProvider>
        <ResetPassword />
      </LanguageProvider>
    </MemoryRouter>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('ResetPassword (reset screen)', () => {
  it('renders in English and hides the code field when the token rides the URL', () => {
    localStorage.setItem('pos-language', 'en');
    renderPage();

    expect(screen.getByText('Choose a new password')).toBeInTheDocument();
    expect(screen.queryByLabelText('Reset code')).not.toBeInTheDocument();
  });

  it('prompts for the reset code when the URL carries no token', () => {
    localStorage.setItem('pos-language', 'en');
    renderPage('/auth/password/reset');

    expect(screen.getByLabelText('Reset code')).toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', () => {
    localStorage.setItem('pos-language', 'ar');
    const { container } = renderPage();

    expect(screen.getByText('اختر كلمة مرور جديدة')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
  });

  it('blocks mismatched passwords without calling the API', () => {
    localStorage.setItem('pos-language', 'en');
    renderPage();

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'GoodPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'Different1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }));

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
    expect(resetPassword).not.toHaveBeenCalled();
  });

  it('submits the token + new password and shows the success state', async () => {
    localStorage.setItem('pos-language', 'en');
    resetPassword.mockResolvedValueOnce({ success: true, message: 'ok' });
    renderPage();

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'GoodPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'GoodPass123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }));

    await waitFor(() => expect(screen.getByText('Password updated')).toBeInTheDocument());
    expect(resetPassword).toHaveBeenCalledWith('abc123', 'GoodPass123');
  });

  it('surfaces the backend message for an invalid/expired token', async () => {
    localStorage.setItem('pos-language', 'en');
    resetPassword.mockRejectedValueOnce({
      response: { data: { detail: 'This reset link is invalid or has expired. Request a new one.' } },
    });
    renderPage();

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'GoodPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'GoodPass123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }));

    await waitFor(() =>
      expect(
        screen.getByText('This reset link is invalid or has expired. Request a new one.')
      ).toBeInTheDocument()
    );
  });
});
