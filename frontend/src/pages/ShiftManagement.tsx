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
import { client, printZReport } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Clock, PlayCircle, StopCircle, History, Receipt } from 'lucide-react';

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

export default function ShiftManagement() {
  const [currentShift, setCurrentShift] = useState<Shift | null>(null);
  const [shiftHistory, setShiftHistory] = useState<Shift[]>([]);
  const [loading, setLoading] = useState(true);
  const [openShiftDialog, setOpenShiftDialog] = useState(false);
  const [closeShiftDialog, setCloseShiftDialog] = useState(false);
  const [openingCash, setOpeningCash] = useState('');
  const [closingCash, setClosingCash] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // RPT-06/PRN-05: id of the shift just closed, so its Z-report can be (re)printed.
  const [lastClosedShiftId, setLastClosedShiftId] = useState<number | null>(null);

  const { t } = useLanguage();

  useEffect(() => {
    loadShiftData();
  }, []);

  async function loadShiftData() {
    setLoading(true);
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
      } else {
        setCurrentShift(null);
      }
    } catch {
      setCurrentShift(null);
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

  async function handleCloseShift() {
    setSubmitting(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/production/shifts/close',
        method: 'POST',
        data: { closing_cash: parseFloat(closingCash) || 0 },
      });
      setCurrentShift(null);
      setCloseShiftDialog(false);
      setClosingCash('');
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Current Shift Status */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Clock className="h-5 w-5 text-blue-400" />
            Current Shift
          </CardTitle>
        </CardHeader>
        <CardContent>
          {currentShift ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <p className="text-slate-400 text-xs">Started</p>
                  <p className="text-white font-medium">{new Date(currentShift.opened_at).toLocaleTimeString()}</p>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <p className="text-slate-400 text-xs">Duration</p>
                  <p className="text-white font-medium">{formatDuration(currentShift.opened_at)}</p>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <p className="text-slate-400 text-xs">Opening Cash</p>
                  <p className="text-white font-medium">SAR {currentShift.opening_cash?.toFixed(2)}</p>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <p className="text-slate-400 text-xs">Transactions</p>
                  <p className="text-white font-medium">{currentShift.transaction_count || 0}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Badge className="bg-green-500/20 text-green-400">Active</Badge>
                {currentShift.staff_name && <span className="text-slate-400 text-sm">Staff: {currentShift.staff_name}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={() => setCloseShiftDialog(true)} className="bg-red-600 hover:bg-red-700 text-white">
                  <StopCircle className="h-4 w-4 mr-2" /> Close Shift
                </Button>
                <Button
                  variant="outline"
                  onClick={() => printZReport()}
                  className="border-slate-600 text-slate-200 hover:bg-slate-700"
                >
                  <Receipt className="h-4 w-4 mr-2" /> {t('x_report')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Clock className="h-12 w-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400 mb-4">No active shift. Open a new shift to start recording transactions.</p>
              <div className="flex items-center justify-center gap-3">
                <Button onClick={() => setOpenShiftDialog(true)} className="bg-green-600 hover:bg-green-700 text-white">
                  <PlayCircle className="h-4 w-4 mr-2" /> Open New Shift
                </Button>
                {lastClosedShiftId != null && (
                  <Button
                    variant="outline"
                    onClick={() => printZReport(lastClosedShiftId)}
                    className="border-slate-600 text-slate-200 hover:bg-slate-700"
                  >
                    <Receipt className="h-4 w-4 mr-2" /> {t('print_last_z_report')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Shift History */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <History className="h-5 w-5 text-purple-400" />
            Shift History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50">
                <tr className="text-slate-400">
                  <th className="p-3 text-start">Date</th>
                  <th className="p-3 text-start">Staff</th>
                  <th className="p-3 text-start">Opening</th>
                  <th className="p-3 text-start">Closing</th>
                  <th className="p-3 text-start">Difference</th>
                  <th className="p-3 text-start">Sales Total</th>
                  <th className="p-3 text-start">Transactions</th>
                  <th className="p-3 text-start">{t('z_report')}</th>
                </tr>
              </thead>
              <tbody>
                {shiftHistory.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-slate-500">No shift history</td>
                  </tr>
                ) : (
                  shiftHistory.map((shift) => (
                    <tr key={shift.id} className="border-t border-slate-700 text-slate-300">
                      <td className="p-3 text-white">{new Date(shift.opened_at).toLocaleDateString()}</td>
                      <td className="p-3">{shift.staff_name || '—'}</td>
                      <td className="p-3">SAR {shift.opening_cash?.toFixed(2)}</td>
                      <td className="p-3">{shift.closing_cash != null ? `SAR ${shift.closing_cash.toFixed(2)}` : '—'}</td>
                      <td className="p-3">
                        {shift.difference != null ? (
                          <span className={shift.difference >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {shift.difference >= 0 ? '+' : ''}SAR {shift.difference.toFixed(2)}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="p-3 text-white font-medium">SAR {shift.sales_total?.toFixed(2) || '0.00'}</td>
                      <td className="p-3">{shift.transaction_count || 0}</td>
                      <td className="p-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => printZReport(Number(shift.id))}
                          className="text-blue-400 hover:bg-slate-700"
                        >
                          <Receipt className="h-4 w-4 mr-1" /> {t('z_report')}
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Open Shift Dialog */}
      <Dialog open={openShiftDialog} onOpenChange={setOpenShiftDialog}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Open New Shift</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Opening Cash Amount (SAR)</label>
              <Input
                type="number"
                value={openingCash}
                onChange={(e) => setOpeningCash(e.target.value)}
                placeholder="0.00"
                className="bg-slate-700 border-slate-600 text-white text-lg"
              />
            </div>
            <p className="text-slate-400 text-sm">Count the cash in the drawer and enter the total amount before starting your shift.</p>
            <Button onClick={handleOpenShift} disabled={submitting} className="w-full bg-green-600 hover:bg-green-700 text-white">
              {submitting ? t('loading') : 'Open Shift'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Close Shift Dialog */}
      <Dialog open={closeShiftDialog} onOpenChange={setCloseShiftDialog}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Close Shift</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {currentShift && (
              <div className="bg-slate-700/50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Opening Cash:</span>
                  <span className="text-white">SAR {currentShift.opening_cash?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Sales Total:</span>
                  <span className="text-white">SAR {currentShift.sales_total?.toFixed(2) || '0.00'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Expected Cash:</span>
                  <span className="text-white font-bold">SAR {((currentShift.opening_cash || 0) + (currentShift.sales_total || 0)).toFixed(2)}</span>
                </div>
              </div>
            )}
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Actual Closing Cash (SAR)</label>
              <Input
                type="number"
                value={closingCash}
                onChange={(e) => setClosingCash(e.target.value)}
                placeholder="0.00"
                className="bg-slate-700 border-slate-600 text-white text-lg"
              />
            </div>
            {closingCash && currentShift && (
              <div className="bg-slate-700/50 rounded-lg p-3">
                <div className="flex justify-between">
                  <span className="text-slate-400">Difference:</span>
                  <span className={
                    (parseFloat(closingCash) - (currentShift.opening_cash || 0) - (currentShift.sales_total || 0)) >= 0
                      ? 'text-green-400 font-bold'
                      : 'text-red-400 font-bold'
                  }>
                    SAR {(parseFloat(closingCash) - (currentShift.opening_cash || 0) - (currentShift.sales_total || 0)).toFixed(2)}
                  </span>
                </div>
              </div>
            )}
            <Button onClick={handleCloseShift} disabled={submitting} className="w-full bg-red-600 hover:bg-red-700 text-white">
              {submitting ? t('loading') : 'Close Shift'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}