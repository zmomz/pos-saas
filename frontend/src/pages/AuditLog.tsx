import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
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
import { Shield, Clock, Filter } from 'lucide-react';

interface AuditEntry {
  id: string;
  user_email?: string;
  action: string;
  details?: string;
  ip_address?: string;
  created_at?: string;
}

// Normalized verbs the backend emits (services/audit_logs.normalize_action) plus
// the `all` sentinel. `auth_failure` surfaces failed-auth attempts.
const ACTION_TYPES = [
  'all',
  'login',
  'logout',
  'create',
  'update',
  'delete',
  'sale',
  'export',
  'auth_failure',
  'other',
];

// Tailwind classes for an action badge, by verb. Destructive/security verbs are
// red, additive green, mutating yellow, auth login brand; everything else neutral.
function actionBadgeClass(action: string): string {
  switch (action) {
    case 'delete':
    case 'auth_failure':
      return 'bg-red-600/20 text-red-400';
    case 'create':
      return 'bg-green-600/20 text-green-400';
    case 'update':
      return 'bg-yellow-600/20 text-yellow-400';
    case 'sale':
    case 'login':
      return 'bg-brand-600/20 text-brand-400';
    default:
      return 'bg-slate-600/20 text-slate-400';
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

  // Translated label for a normalized verb (e.g. `auth_failure` → "Auth Failure").
  // `all` maps to the catch-all "All Actions" sentinel.
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
      // 403 means the account lacks access to the audit log; show the in-page
      // permission state rather than a misleading empty table (UX-02).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no entries" (UX-02).
        setError(true);
      }
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
      <div className="flex items-center justify-center h-64" dir={isRTL ? 'rtl' : 'ltr'}>
        <div className="text-white animate-pulse">{t('loading')}</div>
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
    <div className="space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header Card */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex items-center gap-3">
          <Shield className="h-8 w-8 text-brand-400" />
          <div>
            <h2 className="text-lg font-bold text-white">{t('audit_log')}</h2>
            <p className="text-slate-400 text-sm">
              {logs.length} {t('audit_total_entries')}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <span className="text-sm text-slate-400">{t('audit_filter')}:</span>
        </div>
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-40 bg-slate-800 border-slate-600 text-white">
            <SelectValue placeholder={t('audit_action_type')} />
          </SelectTrigger>
          <SelectContent className="bg-slate-800 border-slate-600">
            {ACTION_TYPES.map((action) => (
              <SelectItem key={action} value={action} className="text-white hover:bg-slate-700">
                {actionLabel(action)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-slate-400" />
          <Input
            type="date"
            dir="ltr"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            placeholder={t('audit_from')}
            className="w-40 bg-slate-800 border-slate-600 text-white"
          />
          <span className="text-slate-400">—</span>
          <Input
            type="date"
            dir="ltr"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            placeholder={t('audit_to')}
            className="w-40 bg-slate-800 border-slate-600 text-white"
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">{t('audit_col_timestamp')}</th>
              <th className="p-3 text-start">{t('audit_col_user')}</th>
              <th className="p-3 text-start">{t('audit_col_action')}</th>
              <th className="p-3 text-start">{t('audit_col_details')}</th>
              <th className="p-3 text-start">{t('audit_col_ip')}</th>
            </tr>
          </thead>
          <tbody>
            {filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-500">
                  {t('no_audit_entries')}
                </td>
              </tr>
            ) : (
              filteredLogs.map((log) => (
                <tr key={log.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3 text-xs whitespace-nowrap" dir="ltr">
                    {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="p-3">{log.user_email || '—'}</td>
                  <td className="p-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${actionBadgeClass(
                        log.action
                      )}`}
                    >
                      {actionLabel(log.action)}
                    </span>
                  </td>
                  <td className="p-3 max-w-[300px] truncate">{log.details || '—'}</td>
                  <td className="p-3 text-xs text-slate-500" dir="ltr">
                    {log.ip_address || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
