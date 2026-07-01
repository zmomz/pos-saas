import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import EmptyState from '@/components/states/EmptyState';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import {
  getOpsHealth,
  getApiUsageStats,
  getOpsMetrics,
  globalSearch,
  getZatcaIntegrity,
  type OpsHealth,
  type ApiUsageStats,
  type OpsMetrics,
  type GlobalSearchResults,
  type ZatcaIntegrityResult,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatNumber, formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  Activity,
  HeartPulse,
  Gauge,
  ShieldCheck,
  Search,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Lock,
  Package,
  UserCheck,
  Receipt,
} from 'lucide-react';

// A single health check renders green when "healthy"; anything else (the backend
// returns "unhealthy: <reason>") is surfaced as a warning, never hidden.
function checkOk(value: string): boolean {
  return value === 'healthy';
}

function statusCode(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status;
}

export default function Operations() {
  const { t, language } = useLanguage();

  // --- Telemetry loaded on mount (each panel reflects its own real state) ---
  const [health, setHealth] = useState<OpsHealth | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [usage, setUsage] = useState<ApiUsageStats | null>(null);
  const [usageError, setUsageError] = useState(false);
  const [metrics, setMetrics] = useState<OpsMetrics | null>(null);
  const [metricsDenied, setMetricsDenied] = useState(false);
  const [metricsError, setMetricsError] = useState(false);
  const [loading, setLoading] = useState(true);

  // --- ZATCA integrity check (on demand) ---
  const [integrity, setIntegrity] = useState<ZatcaIntegrityResult | null>(null);
  const [integrityRunning, setIntegrityRunning] = useState(false);
  const [integrityDenied, setIntegrityDenied] = useState(false);
  const [integrityError, setIntegrityError] = useState(false);

  // --- Global search (on demand) ---
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GlobalSearchResults | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);

  const loadTelemetry = useCallback(async () => {
    setLoading(true);
    setHealthError(false);
    setUsageError(false);
    setMetricsError(false);
    setMetricsDenied(false);

    const [healthRes, usageRes, metricsRes] = await Promise.allSettled([
      getOpsHealth(),
      getApiUsageStats(),
      getOpsMetrics(),
    ]);

    if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
    else setHealthError(true);

    if (usageRes.status === 'fulfilled') setUsage(usageRes.value);
    else setUsageError(true);

    if (metricsRes.status === 'fulfilled') {
      setMetrics(metricsRes.value);
    } else {
      // 403 here is expected for a standard merchant — the performance monitor is
      // platform-admin scoped. Distinguish that from a genuine failure (UX-02).
      if (statusCode(metricsRes.reason) === 403) setMetricsDenied(true);
      else setMetricsError(true);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    loadTelemetry();
  }, [loadTelemetry]);

  async function runIntegrity() {
    setIntegrityRunning(true);
    setIntegrityDenied(false);
    setIntegrityError(false);
    try {
      setIntegrity(await getZatcaIntegrity());
    } catch (err: unknown) {
      // 403 means this isn't a client tenancy (ZATCA is client-scoped).
      if (statusCode(err) === 403) setIntegrityDenied(true);
      else setIntegrityError(true);
    } finally {
      setIntegrityRunning(false);
    }
  }

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearchError(false);
    try {
      setResults(await globalSearch(q, 20));
    } catch {
      setSearchError(true);
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  if (loading) return <LoadingState message={t('loading')} />;

  // Only a total telemetry blackout (every panel failed) reads as a page error;
  // otherwise each panel renders its own state below.
  if (healthError && usageError && metricsError) {
    return <ErrorState message={t('ops_load_error')} onRetry={loadTelemetry} />;
  }

  const checks = health
    ? Object.entries(health.checks).filter(([k]) => k !== 'timestamp')
    : [];
  const healthy = health?.status === 'healthy';

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <Activity className="h-[18px] w-[18px]" />
          </span>
        }
        title={t('ops_title')}
        subtitle={t('ops_subtitle')}
      >
        <Button variant="outline" onClick={loadTelemetry} className="h-11 rounded-[10px]">
          <RefreshCw className="h-4 w-4 me-2" /> {t('refresh')}
        </Button>
      </PageHeading>

      {/* ── System health: the live pulse of the platform (signature element) ── */}
      <Card className="bg-card border-border">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          {healthError ? (
            <div className="flex items-center gap-3 text-warning">
              <XCircle className="h-5 w-5" />
              <span className="text-sm font-medium">{t('ops_load_error')}</span>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    'relative flex h-10 w-10 items-center justify-center rounded-[12px]',
                    healthy ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'
                  )}
                >
                  <HeartPulse className="h-5 w-5" />
                  <span
                    className={cn(
                      'absolute -end-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-card',
                      healthy ? 'bg-success animate-pulse' : 'bg-warning'
                    )}
                  />
                </span>
                <div>
                  <div className="dxr-eyebrow">{t('ops_system_health')}</div>
                  <div className="text-[17px] font-extrabold tracking-tight">
                    {healthy ? t('ops_health_healthy') : t('ops_health_degraded')}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {checks.map(([key, value]) => {
                  const ok = checkOk(value);
                  return (
                    <Badge key={key} className={ok ? 'pill-success' : 'pill-warning'}>
                      {ok ? (
                        <CheckCircle2 className="h-3.5 w-3.5 me-1" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 me-1" />
                      )}
                      {t(`ops_check_${key}`)}
                    </Badge>
                  );
                })}
                {health?.checks.timestamp && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {t('ops_last_checked')}: {formatDateTime(health.checks.timestamp, language)}
                  </span>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* ── API-usage KPIs (owner-scoped metering) ── */}
      {usageError ? (
        <Card className="bg-card border-border">
          <CardContent className="p-5">
            <ErrorState message={t('ops_load_error')} onRetry={loadTelemetry} />
          </CardContent>
        </Card>
      ) : (
        usage && (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
            <StatTile
              icon={Activity}
              label={t('ops_total_requests')}
              value={formatNumber(usage.total_requests, language, 0)}
              tone="brand"
            />
            <StatTile
              icon={Gauge}
              label={t('ops_endpoints_tracked')}
              value={formatNumber(usage.endpoints.length, language, 0)}
              tone="sky"
            />
            <StatTile
              icon={HeartPulse}
              label={t('ops_rate_limit_remaining')}
              value={formatNumber(Math.round(usage.rate_limit.remaining_tokens), language, 0)}
              valueSmall={`/ ${formatNumber(usage.rate_limit.max_tokens, language, 0)}`}
              tone="gold"
            />
          </div>
        )
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── ZATCA invoice-chain integrity (parity #13) ── */}
        <Card className="bg-card border-border">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-start gap-3">
              <span className="dxr-sw dxr-sw-violet h-10 w-10 shrink-0">
                <ShieldCheck className="h-[18px] w-[18px]" />
              </span>
              <div className="min-w-0">
                <h2 className="text-[15px] font-bold tracking-tight">{t('ops_integrity_title')}</h2>
                <p className="text-sm text-muted-foreground">{t('ops_integrity_desc')}</p>
              </div>
            </div>

            <Button onClick={runIntegrity} disabled={integrityRunning} variant="outline">
              <ShieldCheck className="h-4 w-4 me-2" />
              {integrityRunning ? t('loading') : t('ops_run_integrity')}
            </Button>

            {integrityDenied && (
              <p className="text-sm text-muted-foreground" role="status">
                {t('permission_denied')}
              </p>
            )}
            {integrityError && (
              <p className="text-sm text-warning" role="status">
                {t('ops_integrity_failed')}
              </p>
            )}

            {integrity && !integrityDenied && !integrityError && (
              <div
                role="status"
                className={cn(
                  'rounded-md border px-4 py-3',
                  integrity.total === 0
                    ? 'border-border bg-muted/40'
                    : integrity.ok
                    ? 'border-success/40 bg-success/10'
                    : 'border-danger/40 bg-danger/10'
                )}
              >
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {integrity.total === 0 ? (
                    <span className="text-muted-foreground">{t('ops_integrity_empty')}</span>
                  ) : integrity.ok ? (
                    <span className="flex items-center gap-2 text-success">
                      <CheckCircle2 className="h-4 w-4" />
                      {t('ops_integrity_ok').replace('{total}', formatNumber(integrity.total, language, 0))}
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 text-danger">
                      <XCircle className="h-4 w-4" />
                      {t('ops_integrity_broken').replace('{icv}', String(integrity.broken_at ?? '—'))}
                    </span>
                  )}
                </div>
                {integrity.total > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge className={integrity.chain_ok ? 'pill-success' : 'pill-danger'}>
                      {t('ops_integrity_chain')}
                    </Badge>
                    <Badge className={integrity.signatures_ok ? 'pill-success' : 'pill-danger'}>
                      {t('ops_integrity_signatures')}
                    </Badge>
                  </div>
                )}
                {integrity.detail && !integrity.ok && (
                  <p className="mt-2 font-mono text-xs text-muted-foreground break-all">{integrity.detail}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Server performance (platform-admin scoped) ── */}
        <Card className="bg-card border-border">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-start gap-3">
              <span className="dxr-sw dxr-sw-sky h-10 w-10 shrink-0">
                <Gauge className="h-[18px] w-[18px]" />
              </span>
              <div className="min-w-0">
                <h2 className="text-[15px] font-bold tracking-tight">{t('ops_server_performance')}</h2>
              </div>
            </div>

            {metricsDenied ? (
              <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                <Lock className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{t('ops_metrics_admin_only')}</span>
              </div>
            ) : metricsError ? (
              <p className="text-sm text-warning" role="status">
                {t('ops_load_error')}
              </p>
            ) : (
              metrics && (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-[14px] border border-border bg-muted/30 p-3">
                      <div className="dxr-eyebrow">{t('ops_error_rate')}</div>
                      <div className="text-[20px] font-extrabold tabular-nums">
                        {formatNumber(metrics.summary.error_rate, language, 2)}%
                      </div>
                    </div>
                    <div className="rounded-[14px] border border-border bg-muted/30 p-3">
                      <div className="dxr-eyebrow">{t('ops_avg_response')}</div>
                      <div className="text-[20px] font-extrabold tabular-nums">
                        {formatNumber(metrics.summary.avg_response_ms, language, 0)} ms
                      </div>
                    </div>
                    <div className="rounded-[14px] border border-border bg-muted/30 p-3">
                      <div className="dxr-eyebrow">{t('ops_total_requests')}</div>
                      <div className="text-[20px] font-extrabold tabular-nums">
                        {formatNumber(metrics.summary.total_requests, language, 0)}
                      </div>
                    </div>
                  </div>

                  {Object.keys(metrics.endpoints).length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border text-muted-foreground">
                            <th className="text-start p-2">{t('ops_endpoint')}</th>
                            <th className="text-end p-2">{t('ops_avg_response')}</th>
                            <th className="text-end p-2">{t('ops_p95')}</th>
                            <th className="text-end p-2">{t('ops_errors')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(metrics.endpoints)
                            .sort((a, b) => b[1].total_requests - a[1].total_requests)
                            .slice(0, 8)
                            .map(([endpoint, m]) => (
                              <tr key={endpoint} className="border-b border-border/50">
                                <td className="p-2 font-mono text-xs text-foreground/90 break-all">{endpoint}</td>
                                <td className="p-2 text-end tabular-nums">{formatNumber(m.avg_ms, language, 0)}</td>
                                <td className="p-2 text-end tabular-nums">{formatNumber(m.p95_ms, language, 0)}</td>
                                <td className="p-2 text-end tabular-nums">
                                  {m.error_count > 0 ? (
                                    <span className="text-danger">{formatNumber(m.error_count, language, 0)}</span>
                                  ) : (
                                    formatNumber(m.error_count, language, 0)
                                  )}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Global search across products / customers / invoices ── */}
      <Card className="bg-card border-border">
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start gap-3">
            <span className="dxr-sw dxr-sw-brand h-10 w-10 shrink-0">
              <Search className="h-[18px] w-[18px]" />
            </span>
            <div className="min-w-0">
              <h2 className="text-[15px] font-bold tracking-tight">{t('ops_search_title')}</h2>
            </div>
          </div>

          <form onSubmit={runSearch} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('ops_search_placeholder')}
              className="h-11"
              aria-label={t('ops_search_title')}
            />
            <Button type="submit" disabled={searching || !query.trim()} className="h-11 shrink-0">
              <Search className="h-4 w-4 me-2" />
              {searching ? t('loading') : t('ops_search_run')}
            </Button>
          </form>

          {searchError && (
            <p className="text-sm text-warning" role="status">
              {t('ops_load_error')}
            </p>
          )}

          {results && !searchError && (
            results.total_results === 0 ? (
              <EmptyState
                icon={Search}
                message={t('ops_search_empty')}
                description={t('ops_search_empty_desc')}
              />
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  {t('ops_search_count').replace('{count}', formatNumber(results.total_results, language, 0))}
                </p>

                {results.results.products.length > 0 && (
                  <SearchGroup icon={Package} label={t('ops_search_products')}>
                    {results.results.products.map((p) => (
                      <li key={`p-${p.id}`} className="flex items-center justify-between gap-3 py-2">
                        <span className="min-w-0 truncate text-foreground">
                          {p.name}
                          {p.barcode ? (
                            <span className="ms-2 font-mono text-xs text-muted-foreground">{p.barcode}</span>
                          ) : null}
                        </span>
                        {typeof p.price === 'number' && (
                          <span className="shrink-0 tabular-nums text-muted-foreground">
                            {formatMoney(p.price, language)}
                          </span>
                        )}
                      </li>
                    ))}
                  </SearchGroup>
                )}

                {results.results.customers.length > 0 && (
                  <SearchGroup icon={UserCheck} label={t('ops_search_customers')}>
                    {results.results.customers.map((c) => (
                      <li key={`c-${c.id}`} className="flex items-center justify-between gap-3 py-2">
                        <span className="min-w-0 truncate text-foreground">{c.name}</span>
                        <span className="shrink-0 text-muted-foreground">{c.phone || c.email || '—'}</span>
                      </li>
                    ))}
                  </SearchGroup>
                )}

                {results.results.transactions.length > 0 && (
                  <SearchGroup icon={Receipt} label={t('ops_search_transactions')}>
                    {results.results.transactions.map((tx) => (
                      <li key={`t-${tx.id}`} className="flex items-center justify-between gap-3 py-2">
                        <span className="min-w-0 truncate text-foreground">
                          {tx.invoice_number || `#${tx.id}`}
                          {tx.customer_name ? (
                            <span className="ms-2 text-xs text-muted-foreground">{tx.customer_name}</span>
                          ) : null}
                        </span>
                        <span className="shrink-0 tabular-nums text-muted-foreground">
                          {typeof tx.total_amount === 'number' ? formatMoney(tx.total_amount, language) : '—'}
                        </span>
                      </li>
                    ))}
                  </SearchGroup>
                )}
              </div>
            )
          )}
        </CardContent>
      </Card>

      {/* ── API usage by endpoint (owner-scoped) ── */}
      {!usageError && usage && (
        <Card className="bg-card border-border">
          <CardContent className="p-0">
            <div className="flex items-center gap-3 p-5 pb-3">
              <span className="dxr-sw dxr-sw-gold h-10 w-10 shrink-0">
                <Activity className="h-[18px] w-[18px]" />
              </span>
              <h2 className="text-[15px] font-bold tracking-tight">{t('ops_usage_by_endpoint')}</h2>
            </div>
            {usage.endpoints.length === 0 ? (
              <EmptyState icon={Activity} message={t('ops_no_usage')} description={t('ops_no_usage_desc')} />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="text-start p-3">{t('ops_endpoint')}</th>
                      <th className="text-end p-3">{t('ops_requests')}</th>
                      <th className="text-end p-3">{t('ops_avg_response')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...usage.endpoints]
                      .sort((a, b) => b.request_count - a.request_count)
                      .map((row) => (
                        <tr key={row.endpoint} className="border-b border-border/50">
                          <td className="p-3 font-mono text-xs text-foreground/90 break-all">{row.endpoint}</td>
                          <td className="p-3 text-end tabular-nums">{formatNumber(row.request_count, language, 0)}</td>
                          <td className="p-3 text-end tabular-nums">
                            {formatNumber(row.avg_response_time_ms, language, 0)} ms
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SearchGroup({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <ul className="divide-y divide-border/50 text-sm">{children}</ul>
    </div>
  );
}
