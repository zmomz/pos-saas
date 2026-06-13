import { useCallback, useEffect, useState, type ElementType } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import {
  getZatcaDocumentSummary,
  getZatcaDocuments,
  reportPendingZatcaDocuments,
  type ZatcaDocumentSummary,
  type ZatcaDocument,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
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
  signed: 'bg-brand-500/20 text-brand-400',
  reported: 'bg-green-500/20 text-green-400',
  cleared: 'bg-emerald-500/20 text-emerald-400',
  pending: 'bg-amber-500/20 text-amber-400',
  failed: 'bg-red-500/20 text-red-400',
  unknown: 'bg-slate-500/20 text-slate-300',
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
  const { t } = useLanguage();

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
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <ShieldCheck className="h-6 w-6 text-brand-400" />
            {t('zatca_status')}
          </h2>
          <p className="text-slate-400 text-sm mt-1">{t('zatca_status_desc')}</p>
        </div>
        <Button
          variant="outline"
          onClick={load}
          className="border-slate-600 text-slate-300 hover:bg-slate-700"
        >
          <RefreshCw className="h-4 w-4 mr-2" /> {t('refresh')}
        </Button>
      </div>

      {/* Onboarding / gateway state */}
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge className={summary?.onboarded ? STATUS_BADGE.reported : STATUS_BADGE.pending}>
          {summary?.onboarded ? t('zatca_onboarded') : t('zatca_not_onboarded')}
        </Badge>
        <Badge className={summary?.gateway_configured ? STATUS_BADGE.reported : STATUS_BADGE.unknown}>
          {summary?.gateway_configured ? t('zatca_gateway_configured') : t('zatca_gateway_unconfigured')}
        </Badge>
      </div>

      {/* Stuck-document alert (ZA-08 alerting) */}
      {summary?.needs_attention && (
        <div
          role="alert"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-md border border-amber-600/40 bg-amber-500/10 px-4 py-3"
        >
          <div className="flex items-start gap-2 text-amber-300 text-sm">
            <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>
              {t('zatca_stuck_alert')
                .replace('{pending}', String(summary.pending))
                .replace('{failed}', String(summary.failed))}
            </span>
          </div>
          <Button
            onClick={handleReconcile}
            disabled={reconciling || !summary.onboarded}
            className="bg-amber-600 hover:bg-amber-700 text-white shrink-0"
            title={summary.onboarded ? undefined : t('zatca_not_onboarded')}
          >
            {reconciling ? t('loading') : t('zatca_reconcile')}
          </Button>
        </div>
      )}

      {reconcileMsg && (
        <p className="text-sm text-slate-300" role="status">
          {reconcileMsg}
        </p>
      )}

      {/* Status summary cards / empty state */}
      {(summary?.total ?? 0) === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-10 text-center">
            <FileText className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-1">{t('zatca_no_documents')}</h3>
            <p className="text-slate-400 text-sm">{t('zatca_no_documents_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {statuses.map((s) => {
              const Icon = STATUS_ICON[s] || FileText;
              return (
                <Card key={s} className="bg-slate-800 border-slate-700">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-2xl font-bold text-white">{counts[s]}</span>
                      <Icon className="h-5 w-5 text-slate-500" />
                    </div>
                    <Badge className={`mt-2 ${STATUS_BADGE[s] || STATUS_BADGE.unknown}`}>
                      {t(`zatca_doc_${s}`)}
                    </Badge>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Document table */}
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    <th className="text-start p-3">{t('invoice_number')}</th>
                    <th className="text-start p-3">ICV</th>
                    <th className="text-start p-3">{t('status')}</th>
                    <th className="text-start p-3">{t('date')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <tr key={d.id} className="border-b border-slate-700/50">
                      <td className="p-3 text-white">{d.invoice_number}</td>
                      <td className="p-3 text-slate-300">{d.icv ?? '—'}</td>
                      <td className="p-3">
                        <Badge className={STATUS_BADGE[d.status] || STATUS_BADGE.unknown}>
                          {t(`zatca_doc_${d.status}`)}
                        </Badge>
                      </td>
                      <td className="p-3 text-slate-400">
                        {d.created_at ? new Date(d.created_at).toLocaleString() : '—'}
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
