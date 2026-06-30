import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AgentLandingPage from './AgentLandingPage';

// M2 Fix (#234): a prospect must never see "Distributor Not Found" because of a
// transient network/5xx blip — only a genuine 404 is the agent truly being absent.

const BASE = 'http://127.0.0.1:8000';

const PROFILE = {
  company_name: 'Najd POS',
  features: [],
  primary_color: '#006C35',
  contact_email: 'hello@najd.sa',
  contact_phone: '920001234',
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

describe('AgentLandingPage error honesty (#234)', () => {
  it('shows a retry, not "Distributor Not Found", on a 5xx failure', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 })
      )
    );
    renderPage();

    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByText(/Distributor Not Found/i)).not.toBeInTheDocument();
  });

  it('shows a retry, not "Distributor Not Found", on a network error', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () => HttpResponse.error())
    );
    renderPage();

    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByText(/Distributor Not Found/i)).not.toBeInTheDocument();
  });

  it('still shows the not-found state for a genuine 404', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () =>
        HttpResponse.json({ detail: 'missing' }, { status: 404 })
      )
    );
    renderPage();

    expect(await screen.findByText(/Distributor Not Found/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });

  it('retry re-runs the failed load and renders the profile on success', async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 503 })
          : HttpResponse.json(PROFILE);
      })
    );
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /try again/i }));
    expect((await screen.findAllByText('Najd POS')).length).toBeGreaterThan(0);
  });
});

describe('AgentLandingPage CTA contrast guard (#234)', () => {
  it('uses dark text on a pale brand CTA', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () =>
        HttpResponse.json({ ...PROFILE, primary_color: '#FFF3C4' })
      )
    );
    renderPage();

    const cta = (await screen.findAllByRole('button', { name: /start free trial/i }))[0];
    expect((cta as HTMLElement).style.color).toBe('rgb(10, 10, 10)');
  });

  it('uses white text on a dark brand CTA', async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant/agent/7/public`, () =>
        HttpResponse.json({ ...PROFILE, primary_color: '#0B3D2E' })
      )
    );
    renderPage();

    const cta = (await screen.findAllByRole('button', { name: /start free trial/i }))[0];
    expect((cta as HTMLElement).style.color).toBe('rgb(255, 255, 255)');
  });
});
