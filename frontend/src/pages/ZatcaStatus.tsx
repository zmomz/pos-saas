import { useCallback, useEffect, useState, type ElementType } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile, { type TileTone } from '@/components/dashboard/StatTile';
import ZatcaOnboarding from './ZatcaOnboarding';
import {
  getZatcaDocumentSummary,
  getZatcaDocuments,
  reportPendingZatcaDocuments,
  type ZatcaDocumentSummary,
  type ZatcaDocument,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import LoadingState from '@/components/states/LoadingState';
import { formatDateTime } from '@/lib/format';
import {
  ShieldCheck,
  AlertTriangle,
  FileText,
  RefreshCw,
  CheckCircle2,
  Clock,
  XCircle,
} from 'lucide-react';

// Status → tile/badge styling. The fiscal-document state machine is
// signed → reported | cleared, with pending/failed the stuck states (ZA-08).
const STATUS_BADGE: Record<string, string> = {
  signed: 'pill-sky',
  reported: 'pill-success',
  cleared: 'pill-success',
  pending: 'pill-warning',
  failed: 'pill-danger',
  unknown: 'pill-muted',
};

const STATUS_TONE: Record<string, TileTone> = {
  signed: 'sky',
  reported: 'success',
  cleared: 'success',
  pending: 'warning',
  failed: 'warning',
  unknown: 'brand',
};

const STATUS_ICON: Record<string, ElementType> = {
  signed: FileText,
  reported: CheckCircle2,
  cleared: ShieldCheck,
  pending: Clock,
  failed: XCircle,
};

const STATUS_ORDER = ['cleared', 'reported', 'signed', 'pending', 'failed'];

export default function ZatcaStatus() {
  const { t, language } = useLanguage();

  const DOCS_PAGE_SIZE = 50;
  const [summary, setSummary] = useState<ZatcaDocumentSummary | null>(null);
  const [documents, setDocuments] = useState<ZatcaDocument[]>([]);
  const [docsTotal, setDocsTotal] = useState(0);
  const [loadingMoreDocs, setLoadingMoreDocs] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileMsg, setReconcileMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [sum, docs] = await Promise.all([
        getZatcaDocumentSummary(),
        getZatcaDocuments(0, DOCS_PAGE_SIZE),
      ]);
      setSummary(sum);
      setDocuments(docs.items);
      setDocsTotal(docs.total);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 here means the account isn't a client tenancy (ZATCA is client-scoped).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no documents" (UX-02).
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // OPS-05: the document archive is server-side paginated; append the next page.
  async function loadMoreDocs() {
    setLoadingMoreDocs(true);
    try {
      const docs = await getZatcaDocuments(documents.length, DOCS_PAGE_SIZE);
      setDocuments((prev) => [...prev, ...docs.items]);
      setDocsTotal(docs.total);
    } catch {
      // Keep the rows already shown on a transient failure.
    } finally {
      setLoadingMoreDocs(false);
    }
  }

  async function handleReconcile() {
    setReconciling(true);
    setReconcileMsg(null);
    try {
      const res = await reportPendingZatcaDocuments();
      setReconcileMsg(
        t('zatca_reconcile_done')
          .replace('{processed}', String(res.processed))
          .replace('{cleared}', String(res.cleared))
          .replace('{reported}', String(res.reported))
      );
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setReconcileMsg(detail || t('zatca_reconcile_failed'));
    } finally {
      setReconciling(false);
    }
  }

  // ---- Loading state ----
  if (loading) return <LoadingState message={t('loading')} />;

  // ---- Permission-denied state (not a client tenancy) ----
  if (denied) {
    return <PermissionDenied />;
  }

  // ---- Error state (distinct from empty) ----
  if (error) {
    return <ErrorState message={t('zatca_load_error')} onRetry={load} />;
  }

  const counts = summary?.by_status || {};
  const statuses = STATUS_ORDER.filter((s) => counts[s] !== undefined).concat(
    Object.keys(counts).filter((s) => !STATUS_ORDER.includes(s))
  );

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><ShieldCheck className="h-[18px] w-[18px]" /></span>}
        title={t('zatca_status')}
        subtitle={t('zatca_status_desc')}
      >
        <Button
          variant="outline"
          onClick={load}
          className="h-11 rounded-[10px]"
        >
          <RefreshCw className="h-4 w-4 me-2" /> {t('refresh')}
        </Button>
      </PageHeading>

      {/* Onboarding / gateway state */}
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge className={summary?.onboarded ? STATUS_BADGE.reported : STATUS_BADGE.pending}>
          {summary?.onboarded ? t('zatca_onboarded') : t('zatca_not_onboarded')}
        </Badge>
        <Badge className={summary?.gateway_configured ? STATUS_BADGE.reported : STATUS_BADGE.unknown}>
          {summary?.gateway_configured ? t('zatca_gateway_configured') : t('zatca_gateway_unconfigured')}
        </Badge>
      </div>

      {/* In-app onboarding wizard (ISSUE-018) — only while onboarding is incomplete. */}
      {summary && !summary.onboarded && <ZatcaOnboarding onComplete={load} />}

      {/* Stuck-document alert (ZA-08 alerting) */}
      {summary?.needs_attention && (
        <div
          role="alert"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-md border border-warning/40 bg-warning/10 px-4 py-3"
        >
          <div className="flex items-start gap-2 text-warning text-sm">
            <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>
              {t('zatca_stuck_alert')
                .replace('{pending}', String(summary.pending))
                .replace('{failed}', String(summary.failed))}
            </span>
          </div>
          <Button
            onClick={handleReconcile}
            variant="warning"
            disabled={reconciling || !summary.onboarded}
            className="shrink-0"
            title={summary.onboarded ? undefined : t('zatca_not_onboarded')}
          >
            {reconciling ? t('loading') : t('zatca_reconcile')}
          </Button>
        </div>
      )}

      {reconcileMsg && (
        <p className="text-sm text-foreground/90" role="status">
          {reconcileMsg}
        </p>
      )}

      {/* Status summary cards / empty state */}
      {(summary?.total ?? 0) === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('zatca_no_documents')}</h3>
            <p className="text-muted-foreground text-sm">{t('zatca_no_documents_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
            {statuses.map((s) => {
              const Icon = STATUS_ICON[s] || FileText;
              return (
                <StatTile
                  key={s}
                  icon={Icon}
                  label={t(`zatca_doc_${s}`)}
                  value={counts[s]}
                  tone={STATUS_TONE[s] || 'brand'}
                />
              );
            })}
          </div>

          {/* Document table */}
          <Card className="bg-card border-border">
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-start p-3">{t('invoice_number')}</th>
                    <th className="text-start p-3">ICV</th>
                    <th className="text-start p-3">{t('status')}</th>
                    <th className="text-start p-3">{t('date')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <tr key={d.id} className="border-b border-border/50">
                      <td className="p-3 text-foreground">{d.invoice_number}</td>
                      <td className="p-3 text-foreground/90">{d.icv ?? '—'}</td>
                      <td className="p-3">
                        <Badge className={STATUS_BADGE[d.status] || STATUS_BADGE.unknown}>
                          {t(`zatca_doc_${d.status}`)}
                        </Badge>
                      </td>
                      <td className="p-3 text-muted-foreground tabular-nums">
                        {d.created_at ? formatDateTime(d.created_at, language) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {documents.length < docsTotal && (
                <div className="flex justify-center p-4">
                  <Button
                    variant="outline"
                    onClick={loadMoreDocs}
                    disabled={loadingMoreDocs}
                  >
                    {loadingMoreDocs
                      ? t('loading')
                      : `${t('load_more')} (${documents.length}/${docsTotal})`}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
