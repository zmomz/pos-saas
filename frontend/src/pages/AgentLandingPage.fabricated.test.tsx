import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentLandingPage from './AgentLandingPage';

// FE-05 — the public agent storefront must not ship fabricated marketing stats
// or invented customer testimonials. The real product copy (features, pricing,
// the agent's own profile) still renders.

const BASE = 'http://127.0.0.1:8000';

const PROFILE = {
  company_name: 'Najd POS',
  features: [],
  contact_email: 'hello@najd.sa',
  contact_phone: '920001234',
  max_clients: 50,
  active_clients: 12,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/p/7']}>
      <LanguageProvider>
        <Routes>
          <Route path="/p/:agentId" element={<AgentLandingPage />} />
        </Routes>
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentLandingPage fabricated marketing data (FE-05)', () => {
  function mount() {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () =>
        HttpResponse.json(PROFILE)
      )
    );
    renderPage();
  }

  it('renders the real agent profile (sanity)', async () => {
    mount();
    expect((await screen.findAllByText('Najd POS')).length).toBeGreaterThan(0);
  });

  it('does not render fabricated marketing stats', async () => {
    mount();
    await screen.findAllByText('Najd POS');
    expect(screen.queryByText('98%')).not.toBeInTheDocument();
    expect(screen.queryByText('5,000+')).not.toBeInTheDocument();
    expect(screen.queryByText('2.3s')).not.toBeInTheDocument();
    expect(screen.queryByText(/Customer satisfaction/i)).not.toBeInTheDocument();
  });

  it('does not render invented customer testimonials', async () => {
    mount();
    await screen.findAllByText('Najd POS');
    expect(screen.queryByText(/Abu Faisal/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Al-Baik Express/i)).not.toBeInTheDocument();
  });
});
