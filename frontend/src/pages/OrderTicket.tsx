import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  getOrderTicket,
  getTicketItems,
  addTicketItem,
  voidTicketItem,
  fireCourse,
  transferTicket,
  mergeTickets,
  splitTicket,
  getRestaurantTables,
  getOrderTickets,
  getProducts,
  getProductModifierGroups,
  getCombos,
  getPrintRouting,
  getTicketCheck,
  setServiceCharge,
  printTicketCheck,
  settleTicket,
  type OrderTicket as OrderTicketT,
  type TicketItem,
  type RestaurantTable,
  type SplitResult,
  type ProductModifierGroup,
  type Combo,
  type PrintRouting,
  type TicketCheck,
  type SettleResult,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import {
  ClipboardList,
  Plus,
  Trash2,
  Flame,
  ArrowLeftRight,
  Merge,
  SplitSquareHorizontal,
  WifiOff,
  AlertTriangle,
  Lock,
  ArrowLeft,
  Printer,
  Percent,
  Receipt,
  CheckCircle2,
} from 'lucide-react';

const COURSES = ['starters', 'mains', 'dessert', 'drinks'];

const FIRE_BADGE: Record<string, string> = {
  open: 'bg-slate-500/20 text-slate-300',
  fired: 'bg-amber-500/20 text-amber-400',
  bumped: 'bg-green-500/20 text-green-400',
};

interface ProductLite {
  id: number;
  name: string;
  price: number;
}

// Render a line's serialized modifier selection as "Extra cheese, Bacon" (F-056).
function modifierLabel(serialized?: string | null): string {
  if (!serialized) return '';
  try {
    const mods = JSON.parse(serialized);
    if (!Array.isArray(mods)) return '';
    return mods.map((m: { name?: string }) => m.name).filter(Boolean).join(', ');
  } catch {
    return '';
  }
}

export default function OrderTicket() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const { ticketId: ticketIdParam } = useParams<{ ticketId: string }>();
  const ticketId = Number(ticketIdParam);

  const [ticket, setTicket] = useState<OrderTicketT | null>(null);
  const [items, setItems] = useState<TicketItem[]>([]);
  const [products, setProducts] = useState<ProductLite[]>([]);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [otherTickets, setOtherTickets] = useState<OrderTicketT[]>([]);
  const [routing, setRouting] = useState<PrintRouting | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [submitting, setSubmitting] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState<{
    product_id?: number;
    combo_id?: number;
    qty: number;
    course: string;
    seat_no?: number;
    notes: string;
  }>({ qty: 1, course: 'mains', notes: '' });
  // Modifier picker state for the selected product (F-056).
  const [productGroups, setProductGroups] = useState<ProductModifierGroup[]>([]);
  const [selectedMods, setSelectedMods] = useState<Set<number>>(new Set());

  const [transferOpen, setTransferOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [split, setSplit] = useState<SplitResult | null>(null);

  // Service charge (F-061) — % applied outside the VAT base, shown on the check.
  const [check, setCheck] = useState<TicketCheck | null>(null);
  const [scOpen, setScOpen] = useState(false);
  const [scPct, setScPct] = useState(0);

  // Check + settle (F-059): turn the ticket into money and a compliant invoice.
  const [settleOpen, setSettleOpen] = useState(false);
  const [settleMethod, setSettleMethod] = useState('cash');
  // Gratuity entered at settle (POS-13/F-012). Rides on TOP of the invoice total
  // — never part of the VAT base — and is shipped to the settle endpoint, which
  // records it on the sale and renders it on the receipt outside the tax base.
  const [settleTip, setSettleTip] = useState(0);
  const [settled, setSettled] = useState<SettleResult | null>(null);
  const [settleError, setSettleError] = useState<string | null>(null);

  // Connectivity badge (UX-02 offline state).
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [tk, it, prods, tbls, tks, cmb, rt, ck] = await Promise.all([
        getOrderTicket(ticketId),
        getTicketItems(ticketId),
        getProducts(),
        getRestaurantTables(),
        getOrderTickets({ status: 'open' }),
        getCombos().catch(() => [] as Combo[]),
        getPrintRouting(ticketId).catch(() => null),
        getTicketCheck(ticketId).catch(() => null),
      ]);
      setTicket(tk);
      setItems(Array.isArray(it?.items) ? it.items : []);
      setProducts(Array.isArray(prods) ? (prods as ProductLite[]) : []);
      setCombos(Array.isArray(cmb) ? cmb : []);
      setTables(Array.isArray(tbls?.items) ? tbls.items : []);
      setOtherTickets((Array.isArray(tks?.items) ? tks.items : []).filter((o) => o.id !== ticketId));
      setRouting(rt);
      setCheck(ck);
      setScPct(tk?.service_charge_pct ?? 0);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setDenied(true);
      } else {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    load();
  }, [load]);

  // Load the selected product's modifier groups for the picker (F-056).
  async function handleSelectProduct(productId?: number) {
    setSelectedMods(new Set());
    setAddForm((f) => ({ ...f, product_id: productId, combo_id: undefined }));
    if (!productId) {
      setProductGroups([]);
      return;
    }
    try {
      const res = await getProductModifierGroups(productId);
      setProductGroups(Array.isArray(res?.items) ? res.items : []);
    } catch {
      setProductGroups([]);
    }
  }

  function handleSelectCombo(comboId?: number) {
    setSelectedMods(new Set());
    setProductGroups([]);
    setAddForm((f) => ({ ...f, combo_id: comboId, product_id: undefined }));
  }

  function toggleModifier(group: ProductModifierGroup, modId: number) {
    setSelectedMods((prev) => {
      const next = new Set(prev);
      if (next.has(modId)) {
        next.delete(modId);
        return next;
      }
      // Honour the group's max_select: a single-select group replaces its pick.
      const max = group.max_select ?? 1;
      if (max === 1) {
        for (const m of group.modifiers) next.delete(m.id);
      } else if (max && max > 0) {
        const inGroup = group.modifiers.filter((m) => next.has(m.id)).length;
        if (inGroup >= max) return prev; // at the cap; ignore
      }
      next.add(modId);
      return next;
    });
  }

  // Every required group must have a selection before the line can be sent (F-056).
  const requiredUnmet = productGroups
    .filter((g) => g.required)
    .some((g) => !g.modifiers.some((m) => selectedMods.has(m.id)));
  const canAdd = (!!addForm.product_id && !requiredUnmet) || !!addForm.combo_id;

  async function handleAdd() {
    if (!addForm.product_id && !addForm.combo_id) return;
    setSubmitting(true);
    try {
      await addTicketItem(ticketId, {
        product_id: addForm.product_id,
        combo_id: addForm.combo_id,
        qty: addForm.qty || 1,
        course: addForm.course,
        seat_no: addForm.seat_no,
        notes: addForm.notes || undefined,
        modifiers: selectedMods.size ? Array.from(selectedMods) : undefined,
      });
      setAddOpen(false);
      setAddForm({ qty: 1, course: 'mains', notes: '' });
      setProductGroups([]);
      setSelectedMods(new Set());
      await load();
    } catch (err) {
      console.error('Failed to add line:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVoid(item: TicketItem) {
    try {
      await voidTicketItem(ticketId, item.id);
      await load();
    } catch (err) {
      console.error('Failed to void line:', err);
    }
  }

  async function handleFire(course: string) {
    try {
      await fireCourse(ticketId, course);
      await load();
    } catch (err) {
      console.error('Failed to fire course:', err);
    }
  }

  async function handleTransfer(targetTableId: number) {
    setSubmitting(true);
    try {
      await transferTicket(ticketId, targetTableId);
      setTransferOpen(false);
      await load();
    } catch (err) {
      console.error('Failed to transfer ticket:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMerge(sourceTicketId: number) {
    setSubmitting(true);
    try {
      await mergeTickets(ticketId, sourceTicketId);
      setMergeOpen(false);
      await load();
    } catch (err) {
      console.error('Failed to merge tickets:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSplit(strategy: 'seat' | 'amount' | 'item') {
    try {
      const res = await splitTicket(ticketId, strategy, strategy === 'amount' ? 2 : undefined);
      setSplit(res);
    } catch (err) {
      console.error('Failed to split bill:', err);
    }
  }

  async function handleSetServiceCharge() {
    setSubmitting(true);
    try {
      await setServiceCharge(ticketId, scPct || 0);
      setScOpen(false);
      await load();
    } catch (err) {
      console.error('Failed to set service charge:', err);
    } finally {
      setSubmitting(false);
    }
  }

  // Print the non-fiscal proforma (فاتورة مبدئية) — no QR, no stamp (F-059).
  async function handlePrintCheck() {
    try {
      const proforma = await printTicketCheck(ticketId);
      // The always-Arabic 80mm proforma body is returned base64-encoded; a real
      // terminal streams it to the thermal printer. Surface a confirmation here.
      console.info('Proforma printed', proforma.invoice_number ?? proforma.ticket_id);
      window.alert(t('check_printed'));
    } catch (err) {
      console.error('Failed to print check:', err);
    }
  }

  // Settle the ticket into a real ZATCA invoice via the shared sale core (F-059).
  async function handleSettle() {
    setSubmitting(true);
    setSettleError(null);
    try {
      const res = await settleTicket(ticketId, {
        payment_method: settleMethod,
        tip_amount: settleTip || 0,
      });
      setSettled(res);
      setSettleOpen(false);
      await load();
    } catch (err: unknown) {
      // A declined card returns 402 and rolls the whole settlement back: the
      // ticket stays open and the table stays occupied (no invoice minted).
      const status = (err as { response?: { status?: number } })?.response?.status;
      setSettleError(status === 402 ? t('settle_declined') : t('settle_failed'));
    } finally {
      setSubmitting(false);
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

  // ---- Permission-denied state (restaurant mode off / retail business_type) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-slate-500 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-slate-400 text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state (distinct from empty) ----
  if (error || !ticket) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-3" />
            <p className="text-slate-300 mb-4">{t('ticket_load_error')}</p>
            <Button onClick={load} className="bg-brand-600 hover:bg-brand-700 text-white">
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const grandTotal = items.reduce((sum, i) => sum + (i.line_total || 0), 0);
  const freeTables = tables.filter((tb) => (tb.state || 'free') === 'free');

  return (
    <div className="space-y-6">
      {/* Offline banner (UX-02) */}
      {!online && (
        <div className="flex items-center gap-2 rounded-md border border-amber-600/40 bg-amber-500/10 px-4 py-2 text-amber-300 text-sm">
          <WifiOff className="h-4 w-4" />
          <span>{t('you_are_offline')}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <button
            onClick={() => navigate('/floor')}
            className="flex items-center gap-1 text-slate-400 hover:text-white text-sm mb-1"
          >
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> {t('floor_map')}
          </button>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-brand-400" />
            {t('order_ticket')} #{ticket.id}
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            {t(ticket.order_type || 'dine_in')} · {t('status')}: {t('ticket_status_' + (ticket.status || 'open'))}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setAddOpen(true)} className="bg-brand-600 hover:bg-brand-700 text-white">
            <Plus className="h-4 w-4 mr-2" /> {t('add_item')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setTransferOpen(true)}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            <ArrowLeftRight className="h-4 w-4 mr-2" /> {t('transfer')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setMergeOpen(true)}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            <Merge className="h-4 w-4 mr-2" /> {t('merge')}
          </Button>
        </div>
      </div>

      {/* Print routing driven by order_type (F-058) */}
      {routing && routing.targets.length > 0 && (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-slate-400 text-sm">
              <Printer className="h-4 w-4" /> {t('print_routing')}:
            </span>
            {routing.targets.map((target) => (
              <Badge key={target} className="bg-slate-700 text-slate-200">
                {t('print_target_' + target)}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Line items grouped by course */}
      {items.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-10 text-center">
            <ClipboardList className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-1">{t('no_ticket_items')}</h3>
            <p className="text-slate-400 text-sm">{t('no_ticket_items_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {COURSES.filter((c) => items.some((i) => (i.course || 'mains') === c)).map((course) => {
            const courseItems = items.filter((i) => (i.course || 'mains') === course);
            const hasOpen = courseItems.some((i) => (i.fire_state || 'open') === 'open');
            return (
              <Card key={course} className="bg-slate-800 border-slate-700">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-white font-semibold capitalize">{t('course_' + course)}</h3>
                    {hasOpen && (
                      <Button
                        size="sm"
                        onClick={() => handleFire(course)}
                        className="bg-amber-600 hover:bg-amber-700 text-white"
                      >
                        <Flame className="h-4 w-4 mr-1" /> {t('fire_course')}
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {courseItems.map((item) => {
                      const fs = item.fire_state || 'open';
                      return (
                        <div
                          key={item.id}
                          className="flex items-center justify-between rounded-md bg-slate-700/40 px-3 py-2"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-white text-sm">
                                {item.qty} × {item.name || `#${item.product_id}`}
                              </span>
                              <Badge className={FIRE_BADGE[fs] || FIRE_BADGE.open}>
                                {t('fire_state_' + fs)}
                              </Badge>
                              {item.seat_no != null && (
                                <span className="text-xs text-slate-400">
                                  {t('seat')} {item.seat_no}
                                </span>
                              )}
                            </div>
                            {modifierLabel(item.modifiers) && (
                              <p className="text-xs text-brand-300 mt-0.5">+ {modifierLabel(item.modifiers)}</p>
                            )}
                            {item.notes && <p className="text-xs text-slate-400 mt-0.5">{item.notes}</p>}
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-slate-300 text-sm">{item.line_total.toFixed(2)}</span>
                            {fs === 'open' && (
                              <button
                                onClick={() => handleVoid(item)}
                                className="text-slate-400 hover:text-red-400"
                                aria-label={t('void')}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Check breakdown — VAT on goods only, service charge outside the VAT base (F-061) */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-2">
          {check ? (
            <div className="space-y-1.5 text-sm">
              <div className="flex items-center justify-between text-slate-300">
                <span>{t('subtotal')}</span>
                <span>{check.subtotal.toFixed(2)}</span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>{t('vat')}</span>
                <span>{check.vat_amount.toFixed(2)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-slate-700 pt-1.5 text-slate-200">
                <span>{t('total')}</span>
                <span>{check.total_amount.toFixed(2)}</span>
              </div>
              {/* The service charge is its own line, OUTSIDE the VAT base. */}
              <div className="flex items-center justify-between text-slate-300">
                <span className="flex items-center gap-1">
                  {t('service_charge')}
                  {check.service_charge.pct > 0 && (
                    <span className="text-xs text-slate-500">({check.service_charge.pct}%)</span>
                  )}
                  <Badge className="bg-slate-700 text-slate-400 text-[10px]">{t('outside_vat')}</Badge>
                </span>
                <span>{check.service_charge.amount.toFixed(2)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-slate-700 pt-1.5 text-white font-semibold">
                <span>{t('amount_due')}</span>
                <span>{check.amount_due.toFixed(2)}</span>
              </div>
            </div>
          ) : (
            <div className="text-white font-semibold">
              {t('total')}: {grandTotal.toFixed(2)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Settled invoice banner (F-059) — replaces the old browser-only flip */}
      {settled && (
        <Card className="bg-green-900/20 border-green-700/40">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 text-green-400 shrink-0" />
            <div className="text-sm">
              <p className="text-green-300 font-semibold">{t('settled_ok')}</p>
              <p className="text-slate-400">
                {t('invoice_no')}: {settled.invoice_number} ·{' '}
                {t('amount_due')}: {settled.amount_due.toFixed(2)}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {settleError && (
        <div className="flex items-center gap-2 rounded-md border border-red-600/40 bg-red-500/10 px-4 py-2 text-red-300 text-sm">
          <AlertTriangle className="h-4 w-4" />
          <span>{settleError}</span>
        </div>
      )}

      {/* Check + settle (F-059) */}
      {(ticket.status || 'open') !== 'settled' && (ticket.status || 'open') !== 'void' && (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrintCheck}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              <Receipt className="h-4 w-4 mr-1" /> {t('print_check')}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setSettleError(null);
                setSettleTip(0);
                setSettleOpen(true);
              }}
              disabled={items.length === 0}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              <CheckCircle2 className="h-4 w-4 mr-1" /> {t('settle')}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Split + service charge actions */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setScOpen(true)}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            <Percent className="h-4 w-4 mr-1" /> {t('service_charge')}
          </Button>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('seat')}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              <SplitSquareHorizontal className="h-4 w-4 mr-1" /> {t('split_by_seat')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('amount')}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('split_by_amount')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('item')}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('split_by_item')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Add-item dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('add_item')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('product')}</label>
              <select
                value={addForm.product_id ?? ''}
                onChange={(e) => handleSelectProduct(e.target.value ? parseInt(e.target.value) : undefined)}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                <option value="">—</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.price})
                  </option>
                ))}
              </select>
            </div>

            {/* Combo selector (F-056) — a bundle prices the line at its bundle price */}
            {combos.length > 0 && (
              <div>
                <label className="text-sm text-slate-400 mb-1 block">{t('combo')}</label>
                <select
                  value={addForm.combo_id ?? ''}
                  onChange={(e) => handleSelectCombo(e.target.value ? parseInt(e.target.value) : undefined)}
                  className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
                >
                  <option value="">—</option>
                  {combos.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.bundle_price})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Modifier picker (F-056) — required groups must be satisfied */}
            {productGroups.map((g) => {
              const groupSelected = g.modifiers.filter((m) => selectedMods.has(m.id)).length;
              const unmet = g.required && groupSelected === 0;
              return (
                <div key={g.id} className="rounded-md border border-slate-700 p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm text-white">{g.name}</span>
                    {g.required && (
                      <Badge className={unmet ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}>
                        {t('required')}
                      </Badge>
                    )}
                    {g.max_select != null && g.max_select > 1 && (
                      <span className="text-xs text-slate-400">{t('max')} {g.max_select}</span>
                    )}
                  </div>
                  {g.modifiers.length === 0 ? (
                    <p className="text-xs text-slate-500">{t('no_modifiers')}</p>
                  ) : (
                    <div className="space-y-1">
                      {g.modifiers.map((m) => (
                        <label
                          key={m.id}
                          className="flex items-center justify-between gap-2 text-sm text-slate-300 cursor-pointer"
                        >
                          <span className="flex items-center gap-2">
                            <input
                              type={g.max_select === 1 ? 'radio' : 'checkbox'}
                              name={`group-${g.id}`}
                              checked={selectedMods.has(m.id)}
                              onChange={() => toggleModifier(g, m.id)}
                            />
                            {m.name}
                          </span>
                          {m.price_delta !== 0 && (
                            <span className="text-xs text-slate-400">
                              {m.price_delta > 0 ? '+' : ''}
                              {m.price_delta}
                            </span>
                          )}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-slate-400 mb-1 block">{t('quantity')}</label>
                <Input
                  type="number"
                  value={addForm.qty}
                  onChange={(e) => setAddForm((f) => ({ ...f, qty: parseFloat(e.target.value) || 1 }))}
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-sm text-slate-400 mb-1 block">{t('seat')}</label>
                <Input
                  type="number"
                  value={addForm.seat_no ?? ''}
                  onChange={(e) =>
                    setAddForm((f) => ({ ...f, seat_no: e.target.value ? parseInt(e.target.value) : undefined }))
                  }
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('course')}</label>
              <select
                value={addForm.course}
                onChange={(e) => setAddForm((f) => ({ ...f, course: e.target.value }))}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                {COURSES.map((c) => (
                  <option key={c} value={c}>
                    {t('course_' + c)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('note')}</label>
              <Input
                value={addForm.notes}
                onChange={(e) => setAddForm((f) => ({ ...f, notes: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <Button
              onClick={handleAdd}
              disabled={submitting || !canAdd}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white"
            >
              {submitting ? t('loading') : t('add_item')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Transfer dialog */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('transfer_ticket')}</DialogTitle>
          </DialogHeader>
          {freeTables.length === 0 ? (
            <p className="text-slate-400 text-sm">{t('no_free_tables')}</p>
          ) : (
            <div className="space-y-2">
              {freeTables.map((tb) => (
                <Button
                  key={tb.id}
                  variant="outline"
                  disabled={submitting}
                  onClick={() => handleTransfer(tb.id)}
                  className="w-full justify-start border-slate-600 text-slate-300 hover:bg-slate-700"
                >
                  {tb.name}
                </Button>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Merge dialog */}
      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('merge_ticket')}</DialogTitle>
          </DialogHeader>
          {otherTickets.length === 0 ? (
            <p className="text-slate-400 text-sm">{t('no_other_tickets')}</p>
          ) : (
            <div className="space-y-2">
              {otherTickets.map((o) => (
                <Button
                  key={o.id}
                  variant="outline"
                  disabled={submitting}
                  onClick={() => handleMerge(o.id)}
                  className="w-full justify-start border-slate-600 text-slate-300 hover:bg-slate-700"
                >
                  {t('order_ticket')} #{o.id}
                </Button>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Service-charge dialog (F-061) */}
      <Dialog open={scOpen} onOpenChange={setScOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('service_charge')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-slate-400">{t('service_charge_desc')}</p>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('service_charge_pct')}</label>
              <Input
                type="number"
                min={0}
                value={scPct}
                onChange={(e) => setScPct(parseFloat(e.target.value) || 0)}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <Button
              onClick={handleSetServiceCharge}
              disabled={submitting}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white"
            >
              {submitting ? t('loading') : t('apply')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Settle dialog (F-059) — mint a real ZATCA invoice via the sale core */}
      <Dialog open={settleOpen} onOpenChange={setSettleOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('settle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-slate-400">{t('settle_desc')}</p>
            <div className="flex items-center justify-between text-white font-semibold">
              <span>{t('amount_due')}</span>
              <span>{(check?.amount_due ?? grandTotal).toFixed(2)}</span>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('payment_method')}</label>
              <select
                value={settleMethod}
                onChange={(e) => setSettleMethod(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                <option value="cash">{t('pay_cash')}</option>
                <option value="card">{t('pay_card')}</option>
                <option value="mada">Mada</option>
                <option value="applepay">Apple Pay</option>
                <option value="stcpay">STC Pay</option>
              </select>
            </div>
            <div>
              <label htmlFor="settle-tip" className="text-sm text-slate-400 mb-1 block">
                {t('tip')}
              </label>
              <Input
                id="settle-tip"
                type="number"
                min={0}
                step="0.01"
                value={settleTip || ''}
                onChange={(e) => setSettleTip(Math.max(0, Number(e.target.value) || 0))}
                className="bg-slate-700 border-slate-600 text-white"
              />
              <div className="flex gap-2 mt-2">
                {[10, 15, 20].map((pct) => {
                  const base = check?.amount_due ?? grandTotal;
                  return (
                    <Button
                      key={pct}
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setSettleTip(Number(((base * pct) / 100).toFixed(2)))}
                      className="border-slate-600 text-slate-300 hover:bg-slate-700"
                    >
                      {pct}%
                    </Button>
                  );
                })}
              </div>
            </div>
            {settleTip > 0 && (
              <div className="flex items-center justify-between text-white font-semibold">
                <span>{t('total_with_tip')}</span>
                <span>{((check?.amount_due ?? grandTotal) + settleTip).toFixed(2)}</span>
              </div>
            )}
            <Button
              onClick={handleSettle}
              disabled={submitting}
              className="w-full bg-green-600 hover:bg-green-700 text-white"
            >
              {submitting ? t('loading') : t('settle')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Split result dialog */}
      <Dialog open={!!split} onOpenChange={(o) => !o && setSplit(null)}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">
              {t('split_bill')} — {split ? t('split_by_' + split.strategy) : ''}
            </DialogTitle>
          </DialogHeader>
          {split && (
            <div className="space-y-2">
              {split.shares.map((s, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between rounded-md bg-slate-700/40 px-3 py-2 text-sm"
                >
                  <span className="text-slate-300">
                    {s.seat != null
                      ? `${t('seat')} ${s.seat}`
                      : s.name != null
                        ? s.name
                        : `${t('share')} ${s.share}`}
                  </span>
                  <span className="text-white">{s.subtotal.toFixed(2)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-slate-700 pt-2 text-sm font-semibold">
                <span className="text-slate-300">{t('total')}</span>
                <span className="text-white">{split.total.toFixed(2)}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
