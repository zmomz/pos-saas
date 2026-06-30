import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// #202 (parity #1) — an MFA-enabled account does not get logged straight in:
// password login returns a challenge, and the login screen must collect the
// second-factor code and complete it via completeMfaLogin.

const authState = {
  user: null as { role: string } | null,
  loading: false,
  login: vi.fn(),
  completeMfaLogin: vi.fn(),
  loginWithPin: vi.fn(),
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
});

describe('Index login — MFA challenge (#202)', () => {
  it('shows the second-factor step and completes it when login returns a challenge', async () => {
    localStorage.setItem('pos-language', 'en');
    authState.login.mockResolvedValue({ mfaRequired: true, mfaToken: 'ticket-xyz' });
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'Secret123!');
    await user.click(screen.getByRole('button', { name: 'Login' }));

    // The challenge step replaces the password form.
    const codeInput = await screen.findByLabelText('Verification code');
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();

    await user.type(codeInput, '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(authState.completeMfaLogin).toHaveBeenCalledWith('ticket-xyz', '123456')
    );
  });
});
