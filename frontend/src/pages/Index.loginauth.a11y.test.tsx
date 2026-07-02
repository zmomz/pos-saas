import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-275 (a11y · SR pass) — the primary auth entry `/login` (Index.tsx) had
// zero a11y coverage. Two gaps this pins:
//   1. Login failures rendered a bare <p> with no role/aria-live, so a screen
//      reader never announced them (WCAG 4.1.3 Status Messages). Wrapping the
//      message in role="alert" makes assistive tech read it out on appearance.
//   2. The whole password login must be completable with the keyboard only —
//      Tab reaches every field in order and Enter submits the native form.

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

describe('Index login — error announcement (a11y, #275)', () => {
  it('announces a login failure to screen readers via role="alert"', async () => {
    localStorage.setItem('pos-language', 'en');
    authState.login.mockRejectedValue(new Error('Invalid credentials'));
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'wrong-pass');
    await user.click(screen.getByRole('button', { name: 'Login' }));

    // A live region (role="alert" / aria-live) is what an SR announces. A bare
    // <p> would render the text but never announce it — getByRole('alert')
    // resolving is the accessibility guarantee we want.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Invalid credentials');
  });
});

describe('Index login — keyboard-only path (a11y, #275)', () => {
  it('completes a password login using the keyboard only, in tab order', async () => {
    localStorage.setItem('pos-language', 'en');
    authState.login.mockResolvedValue({ user: { role: 'client' } });
    const user = userEvent.setup();

    renderPage();

    const email = screen.getByLabelText('Email') as HTMLInputElement;
    const password = screen.getByLabelText('Password') as HTMLInputElement;

    // Keyboard-only: Tab from the document body until focus lands on the email
    // field — proving it is reachable without a pointer. A bounded loop keeps
    // the assertion resilient to controls that precede it (method tabs).
    for (let i = 0; i < 10 && document.activeElement !== email; i++) {
      await user.tab();
    }
    expect(document.activeElement).toBe(email);

    await user.keyboard('a@b.com');

    // Focus order: the very next tab stop is the password field.
    await user.tab();
    expect(document.activeElement).toBe(password);

    await user.keyboard('Secret123!');

    // Enter submits the native form — no mouse click on the button.
    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(authState.login).toHaveBeenCalledWith('a@b.com', 'Secret123!')
    );
  });
});
