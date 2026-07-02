import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentLandingPage from './AgentLandingPage';

// #269 — the public storefront is PDPL-framed / KSA-first with no GDPR-specific
// implementation. It must not advertise a "GDPR" compliance claim (an unfounded
// legal/marketing liability) in ANY of the four shipped locales, and should
// state the honest PDPL/KSA-first posture instead.

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
  server.use(
    http.get(`${BASE}/api/v1/tenant/agent/7/public`, () => HttpResponse.json(PROFILE))
  );
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
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());

const LANGS = ['en', 'ar', 'hi', 'ur'] as const;

describe('AgentLandingPage PDPL/KSA-first compliance copy (#269)', () => {
  for (const lang of LANGS) {
    it(`does not advertise a GDPR compliance claim in ${lang}`, async () => {
      localStorage.setItem('pos-language', lang);
      renderPage();
      await screen.findAllByText('Najd POS');
      expect(screen.queryByText(/GDPR/i)).not.toBeInTheDocument();
    });
  }

  it('states the honest PDPL/KSA-first posture (en)', async () => {
    localStorage.setItem('pos-language', 'en');
    renderPage();
    await screen.findAllByText('Najd POS');
    expect(screen.getByText(/PDPL/)).toBeInTheDocument();
  });
});
