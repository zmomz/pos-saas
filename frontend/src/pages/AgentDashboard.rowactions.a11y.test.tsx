import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentDashboard from './AgentDashboard';

// M11 · FE-Platform a11y (#226) — screen-reader pass on the agent's merchant book.
//
// Each active merchant row carries a cluster of icon-only controls — Features
// (Sliders glyph), Reset password (KeyRound), the ZATCA toggle (QrCode) and the
// overflow "More actions" (MoreVertical). Every one rendered only a `title`,
// which is an unreliable accessible name for icon-only controls (touch and
// keyboard-only users get no hover tooltip and several screen readers don't
// announce it). WCAG 4.1.2 Name, Role, Value wants an explicit `aria-label`.
// This suite pins that contract on the row-action cluster.

const BASE = 'http://127.0.0.1:8000';

const LIVE = {
  id: 1,
  business_name: 'Live Shop',
  email: 'live@x.co',
  phone: '',
  is_active: true,
  subscription_fee: 100,
  zatca_enabled: true,
  language_preference: 'en',
  archived_at: null,
};

function useHandlers() {
  server.use(
    http.get(`${BASE}/api/v1/tenant/agent/clients`, ({ request }) => {
      const archived = new URL(request.url).searchParams.get('archived') === 'true';
      return HttpResponse.json(
        archived
          ? { items: [], total: 0, remaining_slots: 4 }
          : { items: [LIVE], total: 1, remaining_slots: 4 }
      );
    }),
    http.get(`${BASE}/api/v1/tenant/agent/branding`, () => HttpResponse.json({})),
    http.get(`${BASE}/api/v1/tenant/agent/revenue`, () => HttpResponse.json({ collected: 0, payments: 0, by_client: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/quota`, () => HttpResponse.json({ quota_price: 80, quota_cycle: 'monthly', quota_status: 'active', has_card: false, has_moyasar_account: false, payments: [] })),
    http.get(`${BASE}/api/v1/tenant/agent/commission/statements`, () => HttpResponse.json({ statements: [] }))
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AgentDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentDashboard merchant-row action a11y (#226)', () => {
  it('gives the icon-only Features control an explicit aria-label', async () => {
    useHandlers();
    renderPage();
    await screen.findAllByText('Live Shop');
    const btn = screen.getByRole('button', { name: 'Features' });
    expect(btn).toHaveAttribute('aria-label', 'Features');
  });

  it('gives the icon-only Reset-password control an explicit aria-label', async () => {
    useHandlers();
    renderPage();
    await screen.findAllByText('Live Shop');
    const btn = screen.getByRole('button', { name: 'Reset Password' });
    expect(btn).toHaveAttribute('aria-label', 'Reset Password');
  });

  it('names the icon-only ZATCA toggle for the action it performs (disable, when on)', async () => {
    useHandlers();
    renderPage();
    await screen.findAllByText('Live Shop');
    const btn = screen.getByRole('button', { name: 'Disable ZATCA' });
    expect(btn).toHaveAttribute('aria-label', 'Disable ZATCA');
  });

  it('gives the icon-only overflow "More actions" trigger an explicit aria-label', async () => {
    useHandlers();
    renderPage();
    await screen.findAllByText('Live Shop');
    const btn = screen.getByRole('button', { name: /more actions/i });
    expect(btn).toHaveAttribute('aria-label', 'More actions');
  });
});
