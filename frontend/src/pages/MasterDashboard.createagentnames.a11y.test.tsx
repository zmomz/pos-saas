import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import { PageChromeProvider, useShellChrome } from '@/contexts/PageChromeContext';
import MasterDashboard from './MasterDashboard';

// ISSUE-226 (a11y · SR pass) — the super-admin "Create Agent" dialog renders a
// visible <label> above each field, but the labels carried no `htmlFor` and the
// <Input>s no `id`, so nothing programmatically links them. A placeholder is NOT
// an accessible name (WCAG 1.3.1 Info and Relationships, 4.1.2 Name/Role/Value):
// a screen-reader user tabbing the form heard "edit" with no field name. This
// slice associates each visible label with its input so the SR-announced name
// matches the on-screen label and both localise. getByLabelText resolves an
// associated <label htmlFor>/id but never a placeholder, so a missing link throws.

const BASE = 'http://127.0.0.1:8000';

function economics() {
  return {
    total_agents: 1, active_agents: 0, total_clients: 0, active_clients: 0,
    churned_clients: 0, mrr: 0, arr: 0, churn_rate: 0,
    collected: 0, platform_revenue: 0, by_agent: [],
  };
}

function baseHandlers() {
  return [
    http.get(`${BASE}/api/v1/tenant/master/agents`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/packages/list`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json({ items: [] })),
    http.get(`${BASE}/api/v1/tenant/master/economics`, () => HttpResponse.json(economics())),
  ];
}

// The "Create Agent" button is contributed to the shared shell via
// usePageChrome; the shell (absent in a page-only render) is what paints it. A
// tiny probe reads the registered chrome so the primary action is clickable.
function ChromeProbe() {
  return <>{useShellChrome().primaryAction}</>;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <PageChromeProvider>
          <MasterDashboard />
          <ChromeProbe />
        </PageChromeProvider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

async function openDialog(triggerName: RegExp) {
  const user = userEvent.setup();
  const buttons = await screen.findAllByRole('button', { name: triggerName });
  await user.click(buttons[buttons.length - 1]);
  return within(await screen.findByRole('dialog'));
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MasterDashboard "Create Agent" field accessible names (a11y)', () => {
  it('names the company / email / phone fields in English', async () => {
    server.use(...baseHandlers());
    renderPage();

    const dialog = await openDialog(/Create Agent/i);
    expect(dialog.getByLabelText('Company Name')).toBeInTheDocument();
    expect(dialog.getByLabelText('Email')).toBeInTheDocument();
    expect(dialog.getByLabelText('Phone')).toBeInTheDocument();
  });

  it('localises the accessible names in Arabic with no English leak', async () => {
    localStorage.setItem('pos-language', 'ar');
    server.use(...baseHandlers());
    renderPage();

    const dialog = await openDialog(/إنشاء وكيل/);
    expect(dialog.getByLabelText('اسم الشركة')).toBeInTheDocument();
    expect(dialog.getByLabelText('البريد الإلكتروني')).toBeInTheDocument();
    expect(dialog.getByLabelText('الهاتف')).toBeInTheDocument();

    expect(dialog.queryByLabelText('Company Name')).not.toBeInTheDocument();
    localStorage.clear();
  });
});
