import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import MasterDashboard from './MasterDashboard';

// Issue #211 (M10 Ops): the master operator owns DR posture and must see the
// "last backup" health at a glance. The dashboard fetches
// /tenant/master/ops/backups/health and renders an operable indicator that goes
// red when the latest backup failed (or the newest success is stale/missing).

const BASE = 'http://127.0.0.1:8000';

function economics() {
  return {
    total_agents: 1, active_agents: 1, total_clients: 4, active_clients: 3,
    churned_clients: 1, mrr: 1200, arr: 14400, churn_rate: 0.05, ltv: 8000, cac: null,
    collected: 5000, platform_revenue: 800, by_agent: [],
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

function backupHealth(over: Record<string, unknown> = {}) {
  return {
    status: 'ok',
    last_success_at: '2026-06-30T06:00:00Z',
    last_run_at: '2026-06-30T06:00:00Z',
    last_run_status: 'success',
    age_seconds: 3600,
    total_runs: 12,
    rpo_target_seconds: 86400,
    rto_target_seconds: 14400,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <MasterDashboard />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('MasterDashboard last-backup health indicator (#211)', () => {
  it('surfaces a healthy backup indicator with the last-success time', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/api/v1/tenant/master/ops/backups/health`, () => HttpResponse.json(backupHealth())),
    );
    renderPage();

    const indicator = await screen.findByTestId('backup-health');
    expect(indicator).toBeInTheDocument();
    expect(screen.getByTestId('backup-health-status')).toHaveAttribute('data-status', 'ok');
  });

  it('flags a failing backup so DR posture is not silently red', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/api/v1/tenant/master/ops/backups/health`, () =>
        HttpResponse.json(backupHealth({ status: 'failing', last_run_status: 'failed' }))
      ),
    );
    renderPage();

    const status = await screen.findByTestId('backup-health-status');
    expect(status).toHaveAttribute('data-status', 'failing');
  });

  it('degrades quietly when the health probe fails (never blocks the dashboard)', async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE}/api/v1/tenant/master/ops/backups/health`, () => HttpResponse.error()),
    );
    renderPage();

    // The economics hero still renders even though the backup probe errored.
    expect(await screen.findByTestId('backup-health')).toHaveAttribute('data-status', 'unknown');
  });
});
