import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';
import AgentMoyasarBanner from './AgentMoyasarBanner';

// #235 — the fail-closed banner that makes an agent's unconnected Moyasar
// (a silent revenue stall: every charge 402s, dunning stalls) impossible to miss.

function renderBanner(props: React.ComponentProps<typeof AgentMoyasarBanner>) {
  return render(
    <LanguageProvider>
      <AgentMoyasarBanner {...props} />
    </LanguageProvider>
  );
}

describe('AgentMoyasarBanner', () => {
  it('renders nothing when the provider is connected', () => {
    const { container } = renderBanner({ connected: true, audience: 'merchant' });
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a fail-closed alert to the merchant when the provider is not connected', () => {
    renderBanner({ connected: false, audience: 'merchant' });
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    // Honest, merchant-facing copy: charges can't be processed yet.
    expect(alert.textContent || '').toMatch(/payment|charge/i);
  });

  it('shows the agent a self-directed call to connect when not connected', () => {
    renderBanner({ connected: false, audience: 'agent' });
    const alert = screen.getByRole('alert');
    expect(alert.textContent || '').toMatch(/connect|moyasar/i);
    // It names the blast radius: the whole merchant book can't be charged.
    expect(alert.textContent || '').toMatch(/merchant/i);
  });
});
