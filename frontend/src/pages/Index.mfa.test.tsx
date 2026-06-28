import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-202 — when /auth/login answers with an MFA challenge, the login screen
// swaps the credentials form for a second-factor prompt and only signs in once
// the code is exchanged.
const authState = {
  user: null as { role: string } | null,
  loading: false,
  login: vi.fn(),
  completeMfaLogin: vi.fn(),
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

describe('Index login MFA challenge', () => {
  it('challenges for a code when login returns mfaRequired, then completes', async () => {
    localStorage.setItem('pos-language', 'en');
    authState.login.mockResolvedValue({ mfaRequired: true, mfaToken: 'ticket-1' });
    authState.completeMfaLogin.mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('Email'), 'a@b.c');
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Login' }));

    // The challenge step renders.
    expect(await screen.findByText('Two-step verification')).toBeInTheDocument();

    // Typing the 6-digit code auto-submits via onComplete.
    const otp = screen.getByLabelText('Two-step verification');
    await user.type(otp, '123456');

    await waitFor(() =>
      expect(authState.completeMfaLogin).toHaveBeenCalledWith('ticket-1', '123456')
    );
  });

  it('falls back to a recovery code input', async () => {
    localStorage.setItem('pos-language', 'en');
    authState.login.mockResolvedValue({ mfaRequired: true, mfaToken: 'ticket-2' });
    authState.completeMfaLogin.mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('Email'), 'a@b.c');
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Login' }));

    await screen.findByText('Two-step verification');
    await user.click(screen.getByRole('button', { name: /Use a recovery code instead/i }));

    await user.type(screen.getByLabelText('Recovery code'), 'aaaa-bbbb');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(authState.completeMfaLogin).toHaveBeenCalledWith('ticket-2', 'aaaa-bbbb')
    );
  });
});
