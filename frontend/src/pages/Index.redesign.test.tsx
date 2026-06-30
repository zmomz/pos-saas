import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider } from '@/lib/i18n';

// ISSUE-242 — Login/Index screen redesign: a branded composition (not a generic
// centered form), a password-visibility toggle, the forgot-password link wired,
// the register toggle promoted from an underlined footnote to a deliberate
// affordance, and the bespoke loading block replaced by the shared states.

const authState = {
  user: null as { role: string } | null,
  loading: false,
  login: vi.fn(),
  register: vi.fn(),
  completeMfaLogin: vi.fn(),
  loginWithPin: vi.fn(),
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

describe('Index (login) redesign — issue #242', () => {
  it('presents a branded composition: a dxr-ink panel carrying a product thesis', () => {
    localStorage.setItem('pos-language', 'en');

    const { container } = renderPage();

    // The deliberate brand surface (not a flat centered card).
    expect(container.querySelector('.dxr-ink')).toBeInTheDocument();
    // …carrying a real product thesis, not just stacked fields.
    expect(
      screen.getByText(/run, bill, and grow every store/i)
    ).toBeInTheDocument();
  });

  it('has a password-visibility toggle that flips the field between hidden and shown', () => {
    localStorage.setItem('pos-language', 'en');

    const { container } = renderPage();

    const input = container.querySelector('#password') as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.type).toBe('password');

    const toggle = screen.getByRole('button', { name: /show password/i });
    fireEvent.click(toggle);

    expect(input.type).toBe('text');
    // The control re-labels itself so a screen reader announces the new action.
    expect(screen.getByRole('button', { name: /hide password/i })).toBeInTheDocument();
  });

  it('wires the forgot-password link to the self-serve reset route', () => {
    localStorage.setItem('pos-language', 'en');

    renderPage();

    const link = screen.getByRole('link', { name: /forgot your password/i });
    expect(link).toHaveAttribute('href', '/auth/password/forgot');
  });

  it('replaces the bespoke animate-pulse loading block with the shared loading state', () => {
    localStorage.setItem('pos-language', 'en');
    authState.loading = true;

    const { container } = renderPage();

    // Shared LoadingState renders an aria-live status region…
    expect(screen.getByRole('status')).toBeInTheDocument();
    // …and no bespoke pulse block remains.
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });

  it('promotes the register toggle into a deliberate affordance (not an underlined footnote)', () => {
    localStorage.setItem('pos-language', 'en');

    renderPage();

    const toggle = screen.getByTestId('auth-mode-toggle');
    expect(toggle).toBeInTheDocument();
    // No longer a bare underlined footnote.
    expect(toggle.className).not.toMatch(/\bunderline\b/);
  });
});
