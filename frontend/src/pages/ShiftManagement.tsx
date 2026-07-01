import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  client,
  printZReport,
  recordCashMovement,
  getCashMovements,
  type CashMovement,
  type CashMovementType,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage } from '@/lib/i18n';
import LoadingState from '@/components/states/LoadingState';
import { formatMoney, formatDate, formatTime } from '@/lib/format';
import { Clock, PlayCircle, StopCircle, History, Receipt, ArrowDownCircle, RotateCcw, CalendarCheck } from 'lucide-react';

interface Shift {
  id: string;
  staff_name?: string;
  opening_cash: number;
  closing_cash?: number;
  expected_cash?: number;
  difference?: number;
  sales_total?: number;
  transaction_count?: number;
  status: string;
  opened_at: string;
  closed_at?: string;
}

// POS-09 / F-016: the shift endpoints speak snake_case (`start_time`,
// `total_sales`, `total_transactions`, `cash_difference`) and wrap the current
// shift under `{status, shift}` / the history under `{shifts, total}`. The UI
// model above used `opened_at`/`sales_total`/`difference` and read a flat
// `data.id`, so an open shift never rendered as Active and money columns were
// blank. Normalise every raw payload (current/history/open/close) into the UI
// model here, so the render path stays simple and the reads can't drift again.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeShift(raw: any): Shift {
  return {
    id: String(raw?.id ?? ''),
    staff_name: raw?.staff_name ?? undefined,
    opening_cash: Number(raw?.opening_cash ?? 0),
    closing_cash: raw?.closing_cash != null ? Number(raw.closing_cash) : undefined,
    expected_cash: raw?.expected_cash != null ? Number(raw.expected_cash) : undefined,
    difference:
      raw?.cash_difference != null
        ? Number(raw.cash_difference)
        : raw?.difference != null
          ? Number(raw.difference)
          : undefined,
    sales_total: Number(raw?.total_sales ?? raw?.sales_total ?? 0),
    transaction_count: Number(raw?.total_transactions ?? raw?.transaction_count ?? 0),
    status: raw?.status ?? 'open',
    opened_at: raw?.start_time ?? raw?.opened_at ?? '',
    closed_at: raw?.end_time ?? raw?.closed_at ?? undefined,
  };
}

// Issue #210: the close-readiness checklist returned by GET /shifts/eod-checklist.
// Each blocking item that is not satisfied keeps `ready_to_close` false.
interface EodChecklistItem {
  key: string;
  label: string;
  blocking: boolean;
  satisfied: boolean;
  count: number;
}
interface EodChecklist {
  ready_to_close: boolean;
  items: EodChecklistItem[];
}

// Issue #210: the month-end / year-end period roll-up returned by
// GET /shifts/period-summary (and POST /shifts/period-close). It sums the closed
// shifts in a calendar period and flags whether it is already locked or a drawer
// is still open.
interface PeriodSummary {
  period_type: string;
  period_key: string;
  shifts_count: number;
  opening_cash: number;
  closing_cash: number;
  expected_cash: number;
  cash_difference: number;
  total_sales: number;
  total_transactions: number;
  reconciliation: string;
  already_closed: boolean;
  has_open_shift: boolean;
  // Issue #210: was the inventory reconciled (an approved stocktake) in this period?
  inventory_reconciled: boolean;
  stock_counts_approved: number;
  last_reconciled_at: string | null;
}

export default function ShiftManagement() {
  const [currentShift, setCurrentShift] = useState<Shift | null>(null);
  const [shiftHistory, setShiftHistory] = useState<Shift[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [openShiftDialog, setOpenShiftDialog] = useState(false);
  const [closeShiftDialog, setCloseShiftDialog] = useState(false);
  const [openingCash, setOpeningCash] = useState('');
  const [closingCash, setClosingCash] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // RPT-06/PRN-05: id of the shift just closed, so its Z-report can be (re)printed.
  const [lastClosedShiftId, setLastClosedShiftId] = useState<number | null>(null);
  // FIN-04/POS-09: drawer movements (pay-in/pay-out/cash-drop) on the open shift.
  const [movements, setMovements] = useState<CashMovement[]>([]);
  const [movementDialog, setMovementDialog] = useState(false);
  const [movementType, setMovementType] = useState<CashMovementType>('pay_out');
  const [movementAmount, setMovementAmount] = useState('');
  const [movementReason, setMovementReason] = useState('');
  const [movementError, setMovementError] = useState<string | null>(null);
  // Issue #210: reopen a closed shift to correct a premature/miscounted close.
  const [reopenShiftId, setReopenShiftId] = useState<number | null>(null);
  const [reopenReason, setReopenReason] = useState('');
  const [reopenError, setReopenError] = useState<string | null>(null);
  // Issue #210: the end-of-day checklist gates the close. With a blocking item
  // unsatisfied (a held ticket still parked) the close is refused unless a manager
  // forces it with an audited reason.
  const [eodChecklist, setEodChecklist] = useState<EodChecklist | null>(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [closeError, setCloseError] = useState<string | null>(null);
  // Issue #210: month-end / year-end period close — roll the period's closed
  // shifts into one reconciled summary and lock it.
  const [periodDialog, setPeriodDialog] = useState(false);
  const [periodSummary, setPeriodSummary] = useState<PeriodSummary | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);

  const { t, tt, isRTL, language } = useLanguage();

  useEffect(() => {
    loadShiftData();
  }, []);

  async function loadShiftData() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const currentRes = await client.apiCall.invoke({
        url: '/api/v1/production/shifts/current',
        method: 'GET',
        data: {},
      });
      // `GET /shifts/current` returns {status, shift:{...}} (shift null when none);
      // tolerate a legacy flat shape too. An open shift must render as Active.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const cur: any = currentRes.data;
      const rawShift = cur?.shift ?? (cur?.id != null ? cur : null);
      if (rawShift && rawShift.id != null) {
        setCurrentShift(normalizeShift(rawShift));
        // POS-09/FIN-04: load this shift's drawer movements so the panel renders.
        try {
          const list = await getCashMovements();
          setMovements(list.movements || []);
        } catch {
          setMovements([]);
        }
      } else {
        setCurrentShift(null);
        setMovements([]);
      }
    } catch (err: unknown) {
      setCurrentShift(null);
      setMovements([]);
      // 403 means the account lacks access to shift management; any other failure
      // is a real error. Either way, surface the in-page state instead of a blank
      // shift card and stop — the history read would only repeat the failure (UX-02).
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setDenied(true);
      } else {
        setError(true);
      }
      setShiftHistory([]);
      setLoading(false);
      return;
    }
    try {
      const historyRes = await client.apiCall.invoke({
        url: '/api/v1/production/shifts/history',
        method: 'GET',
        data: { limit: 50 },
      });
      // `GET /shifts/history` returns {shifts:[...], total}; tolerate items/array.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data: any = historyRes.data;
      const rawList = Array.isArray(data?.shifts)
        ? data.shifts
        : Array.isArray(data?.items)
          ? data.items
          : Array.isArray(data)
            ? data
            : [];
      setShiftHistory(rawList.map(normalizeShift));
    } catch {
      setShiftHistory([]);
    }
    setLoading(false);
  }

  async function handleOpenShift() {
    setSubmitting(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/production/shifts/open',
        method: 'POST',
        data: { opening_cash: parseFloat(openingCash) || 0 },
      });
      setCurrentShift(normalizeShift(res.data));
      setOpenShiftDialog(false);
      setOpeningCash('');
      await loadShiftData();
    } catch (err) {
      console.error('Failed to open shift:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function openCloseDialog() {
    setCloseError(null);
    setOverrideReason('');
    setEodChecklist(null);
    setCloseShiftDialog(true);
    // Surface the end-of-day checklist so the cashier sees blocking work (a held
    // ticket still parked) before they count the drawer (#210).
    try {
      const res = await client.apiCall.invoke<EodChecklist>({
        url: '/api/v1/production/shifts/eod-checklist',
        method: 'GET',
      });
      if (res.data) setEodChecklist(res.data);
    } catch (err) {
      console.error('Failed to load EOD checklist:', err);
    }
  }

  async function handleCloseShift() {
    const blocked = eodChecklist != null && !eodChecklist.ready_to_close;
    const reason = overrideReason.trim();
    if (blocked && !reason) {
      setCloseError(tt('sm_close_override_required', 'A reason is required to force the close past the checklist.'));
      return;
    }
    setSubmitting(true);
    setCloseError(null);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/production/shifts/close',
        method: 'POST',
        data: {
          closing_cash: parseFloat(closingCash) || 0,
          ...(blocked ? { override: true, override_reason: reason } : {}),
        },
      });
      setCurrentShift(null);
      setCloseShiftDialog(false);
      setClosingCash('');
      setOverrideReason('');
      setEodChecklist(null);
      if (res.data) {
        setShiftHistory((prev) => [normalizeShift(res.data), ...prev]);
      }
      // POS-09/RPT-06: closing a shift emits its Z-report. The close response
      // carries the shift id directly, so this works regardless of how the
      // current/history reads are shaped.
      const closedId = res.data?.id;
      if (closedId != null) {
        setLastClosedShiftId(Number(closedId));
        try {
          await printZReport(Number(closedId));
        } catch (e) {
          console.error('Failed to print Z-report:', e);
        }
      }
      await loadShiftData();
    } catch (err) {
      console.error('Failed to close shift:', err);
      // Surface the gate so the cashier knows why the close was refused (#210).
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCloseError(detail || tt('sm_close_failed', 'Could not close the shift. Resolve the checklist or try again.'));
    } finally {
      setSubmitting(false);
    }
  }

  function openMovementDialog(type: CashMovementType) {
    setMovementType(type);
    setMovementAmount('');
    setMovementReason('');
    setMovementError(null);
    setMovementDialog(true);
  }

  async function handleRecordMovement() {
    const amount = parseFloat(movementAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setMovementError(t('movement_failed'));
      return;
    }
    setSubmitting(true);
    setMovementError(null);
    try {
      await recordCashMovement({
        movement_type: movementType,
        amount,
        reason: movementReason || undefined,
      });
      setMovementDialog(false);
      await loadShiftData();
    } catch (err) {
      console.error('Failed to record cash movement:', err);
      setMovementError(t('movement_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  function openReopenDialog(shiftId: number) {
    setReopenShiftId(shiftId);
    setReopenReason('');
    setReopenError(null);
  }

  async function handleReopenShift() {
    if (reopenShiftId == null) return;
    const reason = reopenReason.trim();
    if (!reason) {
      setReopenError(tt('sm_reopen_reason_required', 'A reason is required to reopen a shift.'));
      return;
    }
    setSubmitting(true);
    setReopenError(null);
    try {
      await client.apiCall.invoke({
        url: `/api/v1/production/shifts/${reopenShiftId}/reopen`,
        method: 'POST',
        data: { reason },
      });
      setReopenShiftId(null);
      setReopenReason('');
      await loadShiftData();
    } catch (err) {
      console.error('Failed to reopen shift:', err);
      setReopenError(tt('sm_reopen_failed', 'Could not reopen the shift. Make sure no other shift is open.'));
    } finally {
      setSubmitting(false);
    }
  }

  // Issue #210: the period being closed is the current calendar month. The
  // backend keys/locks the period on (year, month); this is the operator's
  // month-end roll-up.
  function currentPeriod() {
    const now = new Date();
    return { period_type: 'month' as const, year: now.getFullYear(), month: now.getMonth() + 1 };
  }

  async function openPeriodDialog() {
    setPeriodError(null);
    setPeriodSummary(null);
    setPeriodDialog(true);
    const { period_type, year, month } = currentPeriod();
    try {
      const res = await client.apiCall.invoke<PeriodSummary>({
        url: '/api/v1/production/shifts/period-summary',
        method: 'GET',
        data: { period_type, year, month },
      });
      if (res.data) setPeriodSummary(res.data);
    } catch (err) {
      console.error('Failed to load period summary:', err);
      setPeriodError(tt('sm_period_load_failed', 'Could not load the period summary.'));
    }
  }

  async function handleClosePeriod() {
    setSubmitting(true);
    setPeriodError(null);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/production/shifts/period-close',
        method: 'POST',
        data: currentPeriod(),
      });
      setPeriodDialog(false);
      setPeriodSummary(null);
      await loadShiftData();
    } catch (err) {
      console.error('Failed to close period:', err);
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPeriodError(detail || tt('sm_period_close_failed', 'Could not close the period.'));
    } finally {
      setSubmitting(false);
    }
  }

  function formatDuration(start: string) {
    const ms = Date.now() - new Date(start).getTime();
    const hours = Math.floor(ms / 3600000);
    const minutes = Math.floor((ms % 3600000) / 60000);
    return `${hours}h ${minutes}m`;
  }

  if (loading) return <LoadingState message={t('loading')} />;

  // A 403 lacks access; any other failure is a real error — show the in-page
  // state rather than a blank shift card (UX-02).
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
        <ErrorState onRetry={loadShiftData} />
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Clock className="h-[18px] w-[18px]" /></span>}
        title={tt('shift_management', 'Shift Management')}
        subtitle={tt('shift_management_desc', 'Open, close and reconcile cashier shifts')}
      />

      {/* Current Shift Status */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <Clock className="h-5 w-5 text-brand" />
            {t('sm_current_shift')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {currentShift ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="bg-muted/50 rounded-lg p-3">
                  <p className="text-muted-foreground text-xs">{t('sm_started')}</p>
                  <p className="text-foreground font-medium tabular-nums">{formatTime(currentShift.opened_at, language)}</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <p className="text-muted-foreground text-xs">{t('sm_duration')}</p>
                  <p className="text-foreground font-medium">{formatDuration(currentShift.opened_at)}</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <p className="text-muted-foreground text-xs">{t('sm_opening_cash')}</p>
                  <p className="text-foreground font-medium tabular-nums">{formatMoney(currentShift.opening_cash || 0, language)}</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <p className="text-muted-foreground text-xs">{t('sm_transactions')}</p>
                  <p className="text-foreground font-medium">{currentShift.transaction_count || 0}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Badge className="pill-success">{t('active')}</Badge>
                {currentShift.staff_name && (
                  <span className="text-muted-foreground text-sm">{t('sm_staff')}: {currentShift.staff_name}</span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="destructive" onClick={openCloseDialog}>
                  <StopCircle className="h-4 w-4 me-2" /> {t('sm_close_shift')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => openMovementDialog('pay_out')}
                  className="border-input text-foreground hover:bg-muted"
                >
                  <ArrowDownCircle className="h-4 w-4 me-2" /> {t('record_cash_movement')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => printZReport()}
                  className="border-input text-foreground hover:bg-muted"
                >
                  <Receipt className="h-4 w-4 me-2" /> {t('x_report')}
                </Button>
              </div>

              {/* Cash drawer movements (FIN-04 / POS-09) for the open shift. */}
              <div className="rounded-lg border border-border">
                <div className="px-3 py-2 border-b border-border text-foreground/90 text-sm font-medium">
                  {t('cash_drawer_movements')}
                </div>
                {movements.length === 0 ? (
                  <p className="px-3 py-4 text-center text-muted-foreground text-sm">{t('no_cash_movements')}</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody>
                      {movements.map((m) => (
                        <tr key={m.id} className="border-t border-border text-foreground/90">
                          <td className="px-3 py-2">
                            <Badge
                              className={m.movement_type === 'pay_in' ? 'pill-success' : 'pill-warning'}
                            >
                              {t(m.movement_type)}
                            </Badge>
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">{m.reason || '—'}</td>
                          <td className="px-3 py-2 text-end text-foreground font-medium tabular-nums">
                            {m.movement_type === 'pay_in' ? '+' : '−'}{formatMoney(Number(m.amount), language)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Clock className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground mb-4">{t('sm_no_active_shift')}</p>
              <div className="flex items-center justify-center gap-3">
                <Button onClick={() => setOpenShiftDialog(true)} variant="success" className="shadow-brand">
                  <PlayCircle className="h-4 w-4 me-2" /> {t('sm_open_new_shift')}
                </Button>
                {lastClosedShiftId != null && (
                  <Button
                    variant="outline"
                    onClick={() => printZReport(lastClosedShiftId)}
                    className="border-input text-foreground hover:bg-muted"
                  >
                    <Receipt className="h-4 w-4 me-2" /> {t('print_last_z_report')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Shift History */}
      <Card className="bg-card border-border">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-foreground flex items-center gap-2">
              <History className="h-5 w-5 text-brand" />
              {t('sm_shift_history')}
            </CardTitle>
            {/* Issue #210: month-end / year-end period close. */}
            <Button variant="outline" size="sm" onClick={openPeriodDialog} className="text-foreground">
              <CalendarCheck className="h-4 w-4 me-1" /> {tt('sm_period_close', 'Period close')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-muted-foreground">
                  <th className="p-3 text-start">{t('sm_date')}</th>
                  <th className="p-3 text-start">{t('sm_staff')}</th>
                  <th className="p-3 text-start">{t('sm_opening')}</th>
                  <th className="p-3 text-start">{t('sm_closing')}</th>
                  <th className="p-3 text-start">{t('sm_difference')}</th>
                  <th className="p-3 text-start">{t('sm_sales_total')}</th>
                  <th className="p-3 text-start">{t('sm_transactions')}</th>
                  <th className="p-3 text-start">{t('z_report')}</th>
                </tr>
              </thead>
              <tbody>
                {shiftHistory.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-muted-foreground">{t('sm_no_history')}</td>
                  </tr>
                ) : (
                  shiftHistory.map((shift) => (
                    <tr key={shift.id} className="border-t border-border text-foreground/90">
                      <td className="p-3 text-foreground tabular-nums">{formatDate(shift.opened_at, language)}</td>
                      <td className="p-3">{shift.staff_name || '—'}</td>
                      <td className="p-3 tabular-nums">{formatMoney(shift.opening_cash || 0, language)}</td>
                      <td className="p-3 tabular-nums">{shift.closing_cash != null ? formatMoney(shift.closing_cash, language) : '—'}</td>
                      <td className="p-3">
                        {shift.difference != null ? (
                          <span className={`tabular-nums ${shift.difference >= 0 ? 'text-success' : 'text-danger'}`}>
                            {shift.difference >= 0 ? '+' : ''}{formatMoney(shift.difference, language)}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="p-3 text-foreground font-medium tabular-nums">{formatMoney(shift.sales_total || 0, language)}</td>
                      <td className="p-3">{shift.transaction_count || 0}</td>
                      <td className="p-3">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => printZReport(Number(shift.id))}
                            className="text-brand hover:bg-muted"
                          >
                            <Receipt className="h-4 w-4 me-1" /> {t('z_report')}
                          </Button>
                          {/* Issue #210: reopen only when no other shift is open
                              (the single-open-drawer invariant). */}
                          {!currentShift && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openReopenDialog(Number(shift.id))}
                              className="text-foreground/80 hover:bg-muted"
                            >
                              <RotateCcw className="h-4 w-4 me-1" /> {tt('sm_reopen', 'Reopen')}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Period Close Dialog (issue #210) */}
      <Dialog open={periodDialog} onOpenChange={setPeriodDialog}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground flex items-center gap-2">
              <CalendarCheck className="h-5 w-5 text-brand" />
              {tt('sm_period_close_title', 'Month-end close')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {periodSummary ? (
              <>
                <div className="bg-muted/50 rounded-lg p-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{tt('sm_period', 'Period')}</span>
                    <span className="text-foreground font-medium tabular-nums">{periodSummary.period_key}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{tt('sm_period_shifts', 'Shifts in period')}</span>
                    <span className="text-foreground tabular-nums">
                      {periodSummary.shifts_count} {tt('sm_period_shifts_unit', 'shift(s)')}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('sm_sales_total')}</span>
                    <span className="text-foreground tabular-nums">{formatMoney(periodSummary.total_sales || 0, language)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('sm_difference')}</span>
                    <span className={`tabular-nums ${(periodSummary.cash_difference || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                      {(periodSummary.cash_difference || 0) >= 0 ? '+' : ''}{formatMoney(periodSummary.cash_difference || 0, language)}
                    </span>
                  </div>
                  {/* Issue #210: inventory reconciliation status for the period. */}
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{tt('sm_period_inventory', 'Inventory')}</span>
                    {periodSummary.inventory_reconciled ? (
                      <span className="text-success font-medium">
                        {tt('sm_period_reconciled', 'Inventory reconciled')}
                        {periodSummary.stock_counts_approved > 1
                          ? ` (${periodSummary.stock_counts_approved})`
                          : ''}
                      </span>
                    ) : (
                      <span className="text-warning font-medium">
                        {tt('sm_period_unreconciled', 'No stock count — un-reconciled')}
                      </span>
                    )}
                  </div>
                </div>
                {periodSummary.already_closed && (
                  <p className="text-sm text-warning">{tt('sm_period_already_closed', 'This period is already closed.')}</p>
                )}
                {periodSummary.has_open_shift && (
                  <p className="text-sm text-warning">{tt('sm_period_has_open', 'Close the open shift before closing the period.')}</p>
                )}
                {periodError && <p className="text-sm text-danger">{periodError}</p>}
                <Button
                  onClick={handleClosePeriod}
                  disabled={submitting || periodSummary.already_closed || periodSummary.has_open_shift}
                  variant="destructive"
                  className="w-full"
                >
                  {submitting ? t('loading') : tt('sm_period_close_confirm', 'Close period')}
                </Button>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">{periodError || t('loading')}</p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Open Shift Dialog */}
      <Dialog open={openShiftDialog} onOpenChange={setOpenShiftDialog}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('sm_open_new_shift')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('sm_opening_cash_amount')}</label>
              <Input
                type="number"
                dir="ltr"
                value={openingCash}
                onChange={(e) => setOpeningCash(e.target.value)}
                placeholder="0.00"
                className="bg-muted border-input text-foreground text-lg"
              />
            </div>
            <p className="text-muted-foreground text-sm">{t('sm_opening_hint')}</p>
            <Button onClick={handleOpenShift} disabled={submitting} variant="success" className="w-full shadow-brand">
              {submitting ? t('loading') : t('sm_open_shift')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Close Shift Dialog */}
      <Dialog open={closeShiftDialog} onOpenChange={setCloseShiftDialog}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('sm_close_shift')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {currentShift && (
              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('sm_opening_cash')}:</span>
                  <span className="text-foreground tabular-nums">{formatMoney(currentShift.opening_cash || 0, language)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('sm_sales_total')}:</span>
                  <span className="text-foreground tabular-nums">{formatMoney(currentShift.sales_total || 0, language)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('sm_expected_cash')}:</span>
                  <span className="text-foreground font-bold tabular-nums">{formatMoney((currentShift.opening_cash || 0) + (currentShift.sales_total || 0), language)}</span>
                </div>
              </div>
            )}
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('sm_closing_cash_amount')}</label>
              <Input
                type="number"
                dir="ltr"
                value={closingCash}
                onChange={(e) => setClosingCash(e.target.value)}
                placeholder="0.00"
                className="bg-muted border-input text-foreground text-lg"
              />
            </div>
            {closingCash && currentShift && (
              <div className="bg-muted/50 rounded-lg p-3">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('sm_difference')}:</span>
                  <span className={
                    (parseFloat(closingCash) - (currentShift.opening_cash || 0) - (currentShift.sales_total || 0)) >= 0
                      ? 'text-success font-bold tabular-nums'
                      : 'text-danger font-bold tabular-nums'
                  }>
                    {formatMoney(parseFloat(closingCash) - (currentShift.opening_cash || 0) - (currentShift.sales_total || 0), language)}
                  </span>
                </div>
              </div>
            )}
            {/* End-of-day checklist (#210): block the close on unfinished work; a
                manager may force it past with an audited reason. */}
            {eodChecklist && eodChecklist.items.length > 0 && (
              <div className="bg-muted/50 rounded-lg p-3 space-y-2">
                <p className="text-sm font-medium text-foreground">
                  {tt('sm_eod_checklist', 'End-of-day checklist')}
                </p>
                {eodChecklist.items.map((item) => (
                  <div key={item.key} className="flex justify-between text-sm">
                    <span className={item.satisfied ? 'text-muted-foreground' : 'text-danger'}>
                      {item.satisfied ? '✓' : '✗'}{' '}
                      {item.key === 'no_held_orders'
                        ? tt('sm_eod_no_held', 'No held tickets outstanding')
                        : item.label}
                    </span>
                    {!item.satisfied && item.count > 0 && (
                      <span className="text-danger tabular-nums">{item.count}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {eodChecklist && !eodChecklist.ready_to_close && (
              <div>
                <label htmlFor="close-override-reason" className="text-sm text-muted-foreground mb-1 block">
                  {tt('sm_close_override_reason', 'Override reason (required to force the close)')}
                </label>
                <Input
                  id="close-override-reason"
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder={tt('sm_close_override_placeholder', 'e.g. end of day; ticket abandoned')}
                  className="bg-muted border-input text-foreground"
                />
              </div>
            )}
            {closeError && <p className="text-danger text-sm">{closeError}</p>}
            <Button variant="destructive" onClick={handleCloseShift} disabled={submitting} className="w-full">
              {submitting
                ? t('loading')
                : eodChecklist && !eodChecklist.ready_to_close
                  ? tt('sm_close_override_confirm', 'Override & Close')
                  : t('sm_close_shift')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reopen Shift Dialog (issue #210) */}
      <Dialog open={reopenShiftId != null} onOpenChange={(open) => { if (!open) setReopenShiftId(null); }}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{tt('sm_reopen_shift', 'Reopen Shift')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-muted-foreground text-sm">
              {tt('sm_reopen_hint', 'Reopening clears the prior close. The reason is recorded in the audit trail.')}
            </p>
            <div>
              <label htmlFor="reopen-reason" className="text-sm text-muted-foreground mb-1 block">
                {tt('sm_reopen_reason', 'Reason for reopening')}
              </label>
              <Input
                id="reopen-reason"
                value={reopenReason}
                onChange={(e) => setReopenReason(e.target.value)}
                placeholder={tt('sm_reopen_reason_placeholder', 'e.g. miscounted the drawer')}
                className="bg-muted border-input text-foreground"
              />
            </div>
            {reopenError && <p className="text-danger text-sm">{reopenError}</p>}
            <Button onClick={handleReopenShift} disabled={submitting} className="w-full" variant="success">
              {submitting ? t('loading') : tt('sm_reopen_confirm', 'Confirm Reopen')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Cash Movement Dialog (FIN-04 / POS-09) */}
      <Dialog open={movementDialog} onOpenChange={setMovementDialog}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('record_cash_movement')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('movement_type')}</label>
              <div className="dxr-seg w-full">
                {(['pay_in', 'pay_out', 'cash_drop'] as CashMovementType[]).map((type) => (
                  <button
                    key={type}
                    type="button"
                    data-active={movementType === type}
                    onClick={() => setMovementType(type)}
                    className="flex-1"
                  >
                    {t(type)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('movement_amount')}</label>
              <Input
                type="number"
                dir="ltr"
                value={movementAmount}
                onChange={(e) => setMovementAmount(e.target.value)}
                placeholder="0.00"
                className="bg-muted border-input text-foreground text-lg"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('movement_reason')}</label>
              <Input
                value={movementReason}
                onChange={(e) => setMovementReason(e.target.value)}
                className="bg-muted border-input text-foreground"
              />
            </div>
            {movementError && (
              <p role="alert" className="text-danger text-sm">
                {movementError}
              </p>
            )}
            <Button
              onClick={handleRecordMovement}
              disabled={submitting}
              className="w-full shadow-brand"
            >
              {submitting ? t('loading') : t('record_cash_movement')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}