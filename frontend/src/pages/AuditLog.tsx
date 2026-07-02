import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { getAuditLogs, getRegulatoryAuditExport, type RegulatoryExportIntegrity } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { Shield, Clock, Filter, Download, ShieldCheck, ShieldAlert } from 'lucide-react';

interface AuditEntry {
  id: string;
  user_email?: string;
  action: string;
  details?: string;
  ip_address?: string;
  created_at?: string;
}

const ACTION_TYPES = [
  'all', 'login', 'logout', 'create', 'update', 'delete', 'sale', 'export', 'auth_failure', 'other',
];

// Semantic pill per verb, mapped to the shared pill-* tones.
function actionPillClass(action: string): string {
  switch (action) {
    case 'delete':
    case 'auth_failure':
      return 'pill-danger';
    case 'create':
    case 'login':
      return 'pill-success';
    case 'update':
      return 'pill-warning';
    default:
      return 'pill-muted';
  }
}

export default function AuditLog() {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [actionFilter, setActionFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // M7·Compliance (#272) — regulatory audit export, fetched lazily on click.
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const [integrity, setIntegrity] = useState<RegulatoryExportIntegrity | null>(null);

  const { t, isRTL, language } = useLanguage();

  // Fetch the tamper-evident audit artifact, surface its integrity attestation,
  // and download it as JSON so the merchant can hand it to a regulator.
  async function handleRegulatoryExport() {
    setExporting(true);
    setExportError(false);
    try {
      const artifact = await getRegulatoryAuditExport();
      setIntegrity(artifact.integrity);
      const blob = new Blob([JSON.stringify(artifact, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `regulatory-audit-export.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to build regulatory export:', err);
      setExportError(true);
    } finally {
      setExporting(false);
    }
  }

  function actionLabel(action: string): string {
    if (action === 'all') return t('audit_all_actions');
    return t(`audit_act_${action}`);
  }

  useEffect(() => {
    loadLogs();
  }, []);

  async function loadLogs() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const data = await getAuditLogs();
      setLogs(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error('Failed to load audit logs:', err);
      setLogs([]);
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else setError(true);
    } finally {
      setLoading(false);
    }
  }

  const filteredLogs = logs.filter((log) => {
    if (actionFilter !== 'all' && log.action !== actionFilter) return false;
    if (dateFrom) {
      const logDate = new Date(log.created_at || '');
      if (logDate < new Date(dateFrom)) return false;
    }
    if (dateTo) {
      const logDate = new Date(log.created_at || '');
      const toDate = new Date(dateTo);
      toDate.setHours(23, 59, 59);
      if (logDate > toDate) return false;
    }
    return true;
  });

  if (loading) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <LoadingState message={t('loading')} />
      </div>
    );
  }

  if (denied) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <PermissionDenied />
      </div>
    );
  }

  if (error) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <ErrorState onRetry={loadLogs} />
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-5" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-9 w-9"><Shield className="h-[18px] w-[18px]" /></span>}
        title={t('audit_log')}
        subtitle={`${logs.length} ${t('audit_total_entries')}`}
      />

      {/* Regulatory export (#272, SEC-05) — tamper-evident artifact + attestation */}
      <div className="dxr-tile flex flex-col gap-3 p-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-4 w-4 text-brand" />
          <div>
            <p className="text-sm font-semibold text-foreground">{t('regulatory_export')}</p>
            <p className="text-xs text-muted-foreground">{t('regulatory_export_hint')}</p>
            {integrity && (
              <p
                className={`mt-1 flex items-center gap-1 text-xs font-medium ${
                  integrity.verified ? 'text-success' : 'text-danger'
                }`}
              >
                {integrity.verified ? (
                  <ShieldCheck className="h-3.5 w-3.5" />
                ) : (
                  <ShieldAlert className="h-3.5 w-3.5" />
                )}
                {integrity.verified ? t('regulatory_verified') : t('regulatory_broken')}
                <span className="text-muted-foreground">
                  · {integrity.checked} {t('regulatory_records_suffix')}
                </span>
              </p>
            )}
            {exportError && (
              <p role="alert" className="mt-1 text-xs text-danger">
                {t('regulatory_export_error')}
              </p>
            )}
          </div>
        </div>
        <Button variant="outline" onClick={handleRegulatoryExport} disabled={exporting} className="shrink-0">
          <Download className="h-4 w-4 me-1" />
          {exporting ? t('loading') : t('regulatory_export_download')}
        </Button>
      </div>

      {/* Filters */}
      <div className="dxr-tile flex flex-col gap-3 p-3.5 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Filter className="h-4 w-4" />
          <span>{t('audit_filter')}</span>
        </div>
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-44"><SelectValue placeholder={t('audit_action_type')} /></SelectTrigger>
          <SelectContent>
            {ACTION_TYPES.map((action) => (
              <SelectItem key={action} value={action}>{actionLabel(action)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <Input type="date" dir="ltr" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} placeholder={t('audit_from')} className="w-40" />
          <span className="text-muted-foreground">—</span>
          <Input type="date" dir="ltr" value={dateTo} onChange={(e) => setDateTo(e.target.value)} placeholder={t('audit_to')} className="w-40" />
        </div>
      </div>

      {/* Table */}
      <div className="dxr-tile p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10.5px] font-bold uppercase tracking-wider rtl:tracking-normal text-muted-foreground/80">
                <th className="px-4 py-3 text-start">{t('audit_col_timestamp')}</th>
                <th className="px-4 py-3 text-start">{t('audit_col_user')}</th>
                <th className="px-4 py-3 text-start">{t('audit_col_action')}</th>
                <th className="px-4 py-3 text-start">{t('audit_col_details')}</th>
                <th className="px-4 py-3 text-start">{t('audit_col_ip')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">{t('no_audit_entries')}</td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <tr key={log.id} className="border-t border-border/70 text-foreground/80 transition-colors hover:bg-muted/40">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground" dir="ltr">
                      {log.created_at ? formatDateTime(log.created_at, language) : '—'}
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">{log.user_email || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={actionPillClass(log.action)}>
                        {actionLabel(log.action)}
                      </span>
                    </td>
                    <td className="max-w-[320px] truncate px-4 py-3" title={log.details || undefined}>{log.details || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground" dir="ltr">{log.ip_address || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
