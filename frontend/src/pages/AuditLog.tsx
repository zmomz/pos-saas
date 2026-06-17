import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getAuditLogs } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { Shield, Clock, Filter } from 'lucide-react';

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

  const { t, isRTL } = useLanguage();

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
      <div className="flex h-64 items-center justify-center" dir={isRTL ? 'rtl' : 'ltr'}>
        <div className="animate-pulse text-muted-foreground">{t('loading')}</div>
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
              <tr className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
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
                      {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">{log.user_email || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={actionPillClass(log.action)}>
                        {actionLabel(log.action)}
                      </span>
                    </td>
                    <td className="max-w-[320px] truncate px-4 py-3">{log.details || '—'}</td>
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
