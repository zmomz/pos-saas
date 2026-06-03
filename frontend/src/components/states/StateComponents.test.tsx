import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';
import OfflineBanner from './OfflineBanner';
import ErrorState from './ErrorState';
import PermissionDenied from './PermissionDenied';

// F-051 (UX-02): the back-office had no offline banner, no in-page permission
// state, and errors collapsed into the empty state. These are the shared
// primitives that close that gap — the offline banner is mounted globally in
// DashboardLayout so it covers every page at once.

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { value, configurable: true });
}

function wrap(ui: React.ReactNode) {
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

afterEach(() => setOnline(true));

describe('OfflineBanner (UX-02 / F-051)', () => {
  it('renders nothing while online', () => {
    setOnline(true);
    const { container } = wrap(<OfflineBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the offline banner when navigator is offline', async () => {
    setOnline(false);
    wrap(<OfflineBanner />);
    // The banner is a live region announcing the loss of connectivity.
    const banner = await screen.findByRole('status');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(/offline/i);
  });
});

describe('shared error / permission states are distinct (UX-02 / F-051)', () => {
  it('ErrorState is an alert with an optional retry action', () => {
    const onRetry = vi.fn();
    wrap(<ErrorState onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('PermissionDenied surfaces a no-access message', () => {
    wrap(<PermissionDenied />);
    expect(screen.getByText(/access/i)).toBeInTheDocument();
  });
});
