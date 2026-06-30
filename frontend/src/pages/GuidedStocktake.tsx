import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Snowflake,
  ScanLine,
  ClipboardCheck,
  ClipboardList,
  Plus,
  ArrowLeft,
  CheckCircle2,
  ListChecks,
  Scale,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import LoadingState from '@/components/states/LoadingState';
import EmptyState from '@/components/states/EmptyState';
import ErrorState from '@/components/states/ErrorState';
import { useLanguage } from '@/lib/i18n';
import { formatDate } from '@/lib/format';
import {
  listStocktakes,
  getStocktake,
  startStocktake,
  freezeStocktake,
  countStocktakeLine,
  approveStocktake,
  cancelStocktake,
  getBranches,
  type StocktakeSession,
  type StocktakeStatus,
  type StocktakeLine,
} from '@/lib/api';

interface BranchOption {
  id: number;
  name: string;
}

const STATUS_PILL: Record<StocktakeStatus, string> = {
  draft: 'pill-muted',
  frozen: 'pill-sky',
  approved: 'pill-success',
  cancelled: 'pill-muted',
};

// The guided sequence — these markers are numbered because the count genuinely is
// an ordered flow (you cannot count before you freeze, or approve before you count).
const STEPS = ['start', 'freeze', 'count', 'variance', 'approve'] as const;

// How far the session has progressed → which step markers read as done.
function phaseOf(status: StocktakeStatus): number {
  if (status === 'draft') return 1; // Start done; Freeze is the next action.
  if (status === 'frozen') return 2; // Start + Freeze done; counting now.
  if (status === 'approved') return STEPS.length; // all done.
  return 0;
}

function varianceTone(variance: number | null): string {
  if (variance == null || variance === 0) return 'pill-muted';
  return variance < 0 ? 'pill-danger' : 'pill-sky';
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

export default function GuidedStocktake() {
  const { t, language } = useLanguage();

  const [sessions, setSessions] = useState<StocktakeSession[]>([]);
  const [branches, setBranches] = useState<BranchOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // null = list view; otherwise the open session detail.
  const [active, setActive] = useState<StocktakeSession | null>(null);
  const [busy, setBusy] = useState(false);

  // Start dialog.
  const [startOpen, setStartOpen] = useState(false);
  const [startBranch, setStartBranch] = useState<string>('none');
  const [startName, setStartName] = useState('');

  // Counting step.
  const [barcode, setBarcode] = useState('');
  const [scanQty, setScanQty] = useState('1');
  const [rowDraft, setRowDraft] = useState<Record<number, string>>({});
  const barcodeRef = useRef<HTMLInputElement>(null);

  const branchName = useCallback(
    (id?: number | null) =>
      id == null ? t('stocktake_all_products') : branches.find((b) => b.id === id)?.name ?? `#${id}`,
    [branches, t],
  );

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [list, branchData] = await Promise.all([listStocktakes(), getBranches()]);
      setSessions(list.items);
      const raw = (branchData as { items?: BranchOption[] })?.items ?? (branchData as BranchOption[]);
      setBranches(Array.isArray(raw) ? raw : []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  async function openSession(id: number) {
    setBusy(true);
    try {
      const detail = await getStocktake(id);
      setActive(detail);
      setRowDraft({});
    } catch {
      toast.error(t('stocktake_load_error'));
    } finally {
      setBusy(false);
    }
  }

  function backToList() {
    setActive(null);
    loadList();
  }

  async function handleStart() {
    setBusy(true);
    try {
      const session = await startStocktake({
        branch_id: startBranch === 'none' ? undefined : Number(startBranch),
        name: startName.trim() || undefined,
      });
      setStartOpen(false);
      setStartName('');
      setStartBranch('none');
      setActive(session);
      setRowDraft({});
    } catch {
      toast.error(t('stocktake_load_error'));
    } finally {
      setBusy(false);
    }
  }

  async function handleFreeze() {
    if (!active) return;
    setBusy(true);
    try {
      const frozen = await freezeStocktake(active.id);
      setActive(frozen);
      // Focus the scanner so the count can begin immediately.
      setTimeout(() => barcodeRef.current?.focus(), 50);
    } catch {
      toast.error(t('stocktake_load_error'));
    } finally {
      setBusy(false);
    }
  }

  // Merge a counted line back into the open session's line list.
  function mergeCountedLine(line: {
    id: number;
    product_id: number;
    product_name?: string | null;
    system_quantity: number;
    counted_quantity: number;
    variance: number;
    counted_at?: string | null;
  }) {
    setActive((prev) => {
      if (!prev) return prev;
      const lines = prev.lines ? [...prev.lines] : [];
      const idx = lines.findIndex((l) => l.product_id === line.product_id);
      const next: StocktakeLine = {
        id: line.id,
        product_id: line.product_id,
        product_name: line.product_name,
        system_quantity: line.system_quantity,
        counted_quantity: line.counted_quantity,
        variance: line.variance,
        counted: true,
        counted_at: line.counted_at,
      };
      if (idx >= 0) lines[idx] = { ...lines[idx], ...next };
      else lines.push(next);
      return { ...prev, lines };
    });
  }

  async function applyCount(opts: { product_id?: number; barcode?: string; counted: number }) {
    if (!active) return;
    try {
      const res = await countStocktakeLine(active.id, {
        product_id: opts.product_id,
        barcode: opts.barcode,
        counted_quantity: opts.counted,
      });
      mergeCountedLine(res);
      return true;
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      toast.error(status === 404 ? t('stk_not_found') : t('stocktake_load_error'));
      return false;
    }
  }

  async function handleScan() {
    const code = barcode.trim();
    const qty = Number(scanQty);
    if (!code || Number.isNaN(qty) || qty < 0) return;
    setBusy(true);
    const ok = await applyCount({ barcode: code, counted: qty });
    setBusy(false);
    if (ok) {
      setBarcode('');
      setScanQty('1');
      barcodeRef.current?.focus();
    }
  }

  async function commitRow(line: StocktakeLine) {
    const raw = rowDraft[line.product_id];
    if (raw == null || raw === '') return;
    const qty = Number(raw);
    if (Number.isNaN(qty) || qty < 0 || qty === line.counted_quantity) return;
    await applyCount({ product_id: line.product_id, counted: qty });
    setRowDraft((prev) => {
      const next = { ...prev };
      delete next[line.product_id];
      return next;
    });
  }

  async function handleApprove() {
    if (!active) return;
    setBusy(true);
    try {
      const approved = await approveStocktake(active.id);
      setActive(approved);
      toast.success(
        t('stk_approved_desc').replace('{posted}', String(approved.adjustments_posted ?? 0)),
      );
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || t('stocktake_load_error'));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!active) return;
    if (!window.confirm(t('stk_discard_confirm'))) return;
    setBusy(true);
    try {
      await cancelStocktake(active.id);
      backToList();
    } catch {
      toast.error(t('stocktake_load_error'));
    } finally {
      setBusy(false);
    }
  }

  // ----- Derived counting metrics for the open session -----
  const lines = useMemo(() => active?.lines ?? [], [active]);
  const counted = useMemo(() => lines.filter((l) => l.counted), [lines]);
  const totalVariance = useMemo(
    () => counted.reduce((sum, l) => sum + (l.variance ?? 0), 0),
    [counted],
  );
  const withVariance = useMemo(
    () => counted.filter((l) => (l.variance ?? 0) !== 0).length,
    [counted],
  );
  const uncounted = lines.length - counted.length;

  // ============================ List view ============================
  if (!active) {
    return (
      <div className="animate-fade-up space-y-6">
        <PageHeading
          icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><ClipboardList className="h-[18px] w-[18px]" /></span>}
          title={t('stocktake')}
          subtitle={t('stocktake_desc')}
        >
          <Button className="h-11 rounded-[10px]" onClick={() => setStartOpen(true)}>
            <Plus className="h-4 w-4 me-2" /> {t('stocktake_start')}
          </Button>
        </PageHeading>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={t('stocktake_load_error')} onRetry={loadList} />
        ) : sessions.length === 0 ? (
          <EmptyState
            icon={ClipboardList}
            message={t('stocktake_empty')}
            description={t('stocktake_empty_desc')}
            action={
              <Button onClick={() => setStartOpen(true)}>
                <Plus className="h-4 w-4 me-2" /> {t('stocktake_start')}
              </Button>
            }
          />
        ) : (
          <Card className="bg-card border-border">
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-start p-3">{t('stocktake_name')}</th>
                    <th className="text-start p-3">{t('branch')}</th>
                    <th className="text-start p-3">{t('status')}</th>
                    <th className="text-start p-3">{t('date')}</th>
                    <th className="text-end p-3" />
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => {
                    const resumable = s.status === 'draft' || s.status === 'frozen';
                    return (
                      <tr
                        key={s.id}
                        className="border-b border-border/50 dxr-hover cursor-pointer"
                        onClick={() => openSession(s.id)}
                      >
                        <td className="p-3 font-medium text-foreground">
                          {s.name || `#${s.id}`}
                        </td>
                        <td className="p-3 text-foreground/90">{branchName(s.branch_id)}</td>
                        <td className="p-3">
                          <Badge className={STATUS_PILL[s.status]}>{t(`stk_${s.status}`)}</Badge>
                        </td>
                        <td className="p-3 text-muted-foreground tabular-nums">
                          {s.created_at ? formatDate(s.created_at, language) : '—'}
                        </td>
                        <td className="p-3 text-end">
                          <Button
                            variant={resumable ? 'default' : 'outline'}
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              openSession(s.id);
                            }}
                          >
                            {resumable ? t('stocktake_resume') : t('stk_view')}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {/* Start dialog */}
        <Dialog open={startOpen} onOpenChange={setStartOpen}>
          <DialogContent className="bg-card border-border text-foreground">
            <DialogHeader>
              <DialogTitle className="text-foreground">{t('stocktake_start')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground">{t('stocktake_branch_scope')}</label>
                <Select value={startBranch} onValueChange={setStartBranch}>
                  <SelectTrigger className="bg-muted border-input text-foreground">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-input">
                    <SelectItem value="none">{t('stocktake_all_products')}</SelectItem>
                    {branches.map((b) => (
                      <SelectItem key={b.id} value={String(b.id)}>
                        {b.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground">{t('stocktake_name')}</label>
                <Input
                  value={startName}
                  onChange={(e) => setStartName(e.target.value)}
                  placeholder={t('stocktake_name_placeholder')}
                  className="bg-muted border-input text-foreground"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setStartOpen(false)} disabled={busy}>
                {t('cancel')}
              </Button>
              <Button onClick={handleStart} disabled={busy}>
                {t('stocktake_start')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ============================ Detail view ============================
  const phase = phaseOf(active.status);

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><ClipboardList className="h-[18px] w-[18px]" /></span>}
        title={active.name || `${t('stocktake')} #${active.id}`}
        subtitle={`${branchName(active.branch_id)} · ${t(`stk_${active.status}`)}`}
      >
        <Button variant="outline" className="h-11 rounded-[10px]" onClick={backToList}>
          <ArrowLeft className="h-4 w-4 me-2 rtl:-scale-x-100" /> {t('stk_back_to_list')}
        </Button>
        {(active.status === 'draft' || active.status === 'frozen') && (
          <Button variant="outline" className="h-11 rounded-[10px] text-danger" onClick={handleCancel} disabled={busy}>
            <Trash2 className="h-4 w-4 me-2" /> {t('stk_discard')}
          </Button>
        )}
      </PageHeading>

      {/* Signature element: the guided stepper. */}
      <Card className="bg-card border-border">
        <CardContent className="p-4">
          <ol className="flex items-center gap-1 sm:gap-2 overflow-x-auto">
            {STEPS.map((step, i) => {
              const done = i < phase;
              const activeStep = i === phase;
              return (
                <li key={step} className="flex items-center gap-1 sm:gap-2 shrink-0">
                  <span
                    className={[
                      'flex h-8 w-8 items-center justify-center rounded-full text-[13px] font-bold transition-colors',
                      done
                        ? 'bg-primary text-primary-foreground'
                        : activeStep
                          ? 'bg-gold text-gold-900 ring-2 ring-gold/40'
                          : 'bg-muted text-muted-foreground',
                    ].join(' ')}
                  >
                    {done ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
                  </span>
                  <span
                    className={[
                      'text-[13px] font-medium',
                      done || activeStep ? 'text-foreground' : 'text-muted-foreground',
                    ].join(' ')}
                  >
                    {t(`stk_step_${step}`)}
                  </span>
                  {i < STEPS.length - 1 && (
                    <span className="mx-1 h-px w-5 sm:w-8 bg-border shrink-0" aria-hidden />
                  )}
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      {/* ---- Draft: freeze the baseline ---- */}
      {active.status === 'draft' && (
        <Card className="bg-card border-border">
          <CardContent className="flex flex-col items-center gap-4 p-10 text-center">
            <span className="dxr-sw dxr-sw-gold h-14 w-14"><Snowflake className="h-6 w-6" /></span>
            <div className="space-y-1">
              <h3 className="text-lg font-semibold text-foreground">{t('stk_freeze_title')}</h3>
              <p className="max-w-md text-sm text-muted-foreground">{t('stk_freeze_desc')}</p>
            </div>
            <Button onClick={handleFreeze} disabled={busy} className="h-11">
              <Snowflake className="h-4 w-4 me-2" /> {t('stk_freeze_action')}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ---- Frozen: count + review + approve ---- */}
      {active.status === 'frozen' && (
        <>
          {/* Scan box */}
          <Card className="bg-card border-border">
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2">
                <span className="dxr-sw dxr-sw-brand h-9 w-9"><ScanLine className="h-[18px] w-[18px]" /></span>
                <div>
                  <h3 className="font-semibold text-foreground">{t('stk_count_title')}</h3>
                  <p className="text-[13px] text-muted-foreground">{t('stk_count_desc')}</p>
                </div>
              </div>
              <form
                className="flex flex-col gap-2 sm:flex-row"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleScan();
                }}
              >
                <Input
                  ref={barcodeRef}
                  value={barcode}
                  onChange={(e) => setBarcode(e.target.value)}
                  placeholder={t('stk_scan_placeholder')}
                  className="bg-muted border-input text-foreground sm:flex-1"
                  autoFocus
                />
                <Input
                  type="number"
                  min={0}
                  inputMode="numeric"
                  value={scanQty}
                  onChange={(e) => setScanQty(e.target.value)}
                  className="bg-muted border-input text-foreground sm:w-28 tabular-nums"
                  aria-label={t('counted_quantity')}
                />
                <Button type="submit" disabled={busy || !barcode.trim()} className="sm:w-auto">
                  {t('stk_record_count')}
                </Button>
              </form>
              {/* Progress meter */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[13px] text-muted-foreground">
                  <span>
                    {t('stk_count_progress')
                      .replace('{counted}', String(counted.length))
                      .replace('{total}', String(lines.length))}
                  </span>
                  <span className="tabular-nums">
                    {lines.length ? Math.round((counted.length / lines.length) * 100) : 0}%
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${lines.length ? (counted.length / lines.length) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Variance summary */}
          <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
            <StatTile icon={ListChecks} label={t('stk_items_counted')} value={`${counted.length}/${lines.length}`} tone="brand" />
            <StatTile icon={Scale} label={t('stk_with_variance')} value={withVariance} tone={withVariance ? 'warning' : 'success'} />
            <StatTile icon={ClipboardCheck} label={t('stk_net_variance')} value={signed(totalVariance)} tone={totalVariance < 0 ? 'warning' : totalVariance > 0 ? 'sky' : 'success'} />
            <StatTile icon={ClipboardList} label={t('stk_uncounted_note').replace('{n}', String(uncounted)).split('—')[0].trim()} value={uncounted} tone="violet" />
          </div>

          {/* Lines table */}
          <Card className="bg-card border-border">
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-start p-3">{t('product')}</th>
                    <th className="text-end p-3">{t('system_quantity')}</th>
                    <th className="text-end p-3">{t('counted_quantity')}</th>
                    <th className="text-end p-3">{t('variance')}</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.id} className="border-b border-border/50">
                      <td className="p-3 text-foreground">{line.product_name || `#${line.product_id}`}</td>
                      <td className="p-3 text-end text-foreground/90 tabular-nums">{line.system_quantity}</td>
                      <td className="p-3 text-end">
                        <Input
                          type="number"
                          min={0}
                          inputMode="numeric"
                          value={rowDraft[line.product_id] ?? (line.counted_quantity ?? '')}
                          onChange={(e) =>
                            setRowDraft((prev) => ({ ...prev, [line.product_id]: e.target.value }))
                          }
                          onBlur={() => commitRow(line)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                          }}
                          className="ms-auto h-9 w-24 bg-muted border-input text-foreground text-end tabular-nums"
                          aria-label={`${t('counted_quantity')} — ${line.product_name ?? line.product_id}`}
                        />
                      </td>
                      <td className="p-3 text-end">
                        {line.counted ? (
                          <Badge className={varianceTone(line.variance)}>{signed(line.variance ?? 0)}</Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Approve */}
          <Card className="bg-card border-border">
            <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <h3 className="font-semibold text-foreground">{t('stk_review_title')}</h3>
                <p className="max-w-xl text-[13px] text-muted-foreground">{t('stk_approve_desc')}</p>
                {uncounted > 0 && (
                  <p className="text-[13px] text-warning">
                    {t('stk_uncounted_note').replace('{n}', String(uncounted))}
                  </p>
                )}
              </div>
              <Button onClick={handleApprove} disabled={busy || counted.length === 0} className="h-11 shrink-0">
                <ClipboardCheck className="h-4 w-4 me-2" /> {t('stk_approve_action')}
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {/* ---- Approved: read-only summary ---- */}
      {active.status === 'approved' && (
        <>
          <Card className="bg-card border-border">
            <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
              <span className="dxr-sw dxr-sw-success h-14 w-14"><CheckCircle2 className="h-6 w-6" /></span>
              <div className="space-y-1">
                <h3 className="text-lg font-semibold text-foreground">{t('stk_approved_title')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('stk_approved_desc').replace(
                    '{posted}',
                    String(active.adjustments_posted ?? counted.length),
                  )}
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
            <StatTile icon={ListChecks} label={t('stk_items_counted')} value={`${counted.length}/${lines.length}`} tone="brand" />
            <StatTile icon={Scale} label={t('stk_with_variance')} value={withVariance} tone={withVariance ? 'warning' : 'success'} />
            <StatTile icon={ClipboardCheck} label={t('stk_net_variance')} value={signed(totalVariance)} tone={totalVariance < 0 ? 'warning' : totalVariance > 0 ? 'sky' : 'success'} />
            <StatTile icon={ClipboardList} label={t('date')} value={active.approved_at ? formatDate(active.approved_at, language) : '—'} tone="violet" />
          </div>

          <Card className="bg-card border-border">
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-start p-3">{t('product')}</th>
                    <th className="text-end p-3">{t('system_quantity')}</th>
                    <th className="text-end p-3">{t('counted_quantity')}</th>
                    <th className="text-end p-3">{t('variance')}</th>
                  </tr>
                </thead>
                <tbody>
                  {counted.map((line) => (
                    <tr key={line.id} className="border-b border-border/50">
                      <td className="p-3 text-foreground">{line.product_name || `#${line.product_id}`}</td>
                      <td className="p-3 text-end text-foreground/90 tabular-nums">{line.system_quantity}</td>
                      <td className="p-3 text-end text-foreground tabular-nums">{line.counted_quantity}</td>
                      <td className="p-3 text-end">
                        <Badge className={varianceTone(line.variance)}>{signed(line.variance ?? 0)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
