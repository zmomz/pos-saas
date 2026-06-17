import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  settleTicketPartial,
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
import { formatMoney } from '@/lib/format';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import {
  ClipboardList,
  Plus,
  Trash2,
  Flame,
  ArrowLeftRight,
  Merge,
  SplitSquareHorizontal,
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
  open: 'pill-muted',
  fired: 'pill-warning',
  bumped: 'pill-success',
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
  const { t, language } = useLanguage();
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
  // Partial settlement (ISSUE-070): the server can bill the WHOLE remainder
  // (full /settle) or a subset — a single seat's lines or specific lines — each
  // subset minting its own ZATCA invoice and leaving the rest open.
  const [settleScope, setSettleScope] = useState<'full' | 'seat' | 'item'>('full');
  const [settleSeat, setSettleSeat] = useState<number | undefined>(undefined);
  const [settleItemIds, setSettleItemIds] = useState<Set<number>>(new Set());

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
  // A partial scope (ISSUE-070) bills only a seat / chosen lines through the
  // settle-partial endpoint, leaving the unpaid remainder on the open ticket.
  async function handleSettle() {
    setSubmitting(true);
    setSettleError(null);
    try {
      const res =
        settleScope === 'seat'
          ? await settleTicketPartial(ticketId, {
              seat_no: settleSeat,
              payment_method: settleMethod,
              tip_amount: settleTip || 0,
            })
          : settleScope === 'item'
            ? await settleTicketPartial(ticketId, {
                item_ids: Array.from(settleItemIds),
                payment_method: settleMethod,
                tip_amount: settleTip || 0,
              })
            : await settleTicket(ticketId, {
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
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (restaurant mode off / retail business_type) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-muted-foreground text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state (distinct from empty) ----
  if (error || !ticket) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-danger mx-auto mb-3" />
            <p className="text-foreground/90 mb-4">{t('ticket_load_error')}</p>
            <Button onClick={load}>
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const grandTotal = items.reduce((sum, i) => sum + (i.line_total || 0), 0);
  const freeTables = tables.filter((tb) => (tb.state || 'free') === 'free');

  // Partial-settlement helpers (ISSUE-070): distinct seats on the ticket, the
  // selected subset's goods total (a pre-settle estimate — the authoritative
  // amount_due, incl. VAT proration, comes back on the minted invoice), and
  // whether the current scope selection is settle-able.
  const seatNumbers = Array.from(
    new Set(items.map((i) => i.seat_no).filter((s): s is number => s != null))
  ).sort((a, b) => a - b);
  const settleBase =
    settleScope === 'seat'
      ? items.filter((i) => i.seat_no === settleSeat).reduce((s, i) => s + (i.line_total || 0), 0)
      : settleScope === 'item'
        ? items.filter((i) => settleItemIds.has(i.id)).reduce((s, i) => s + (i.line_total || 0), 0)
        : check?.amount_due ?? grandTotal;
  const canSettle =
    settleScope === 'full' ||
    (settleScope === 'seat' && settleSeat != null) ||
    (settleScope === 'item' && settleItemIds.size > 0);

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <button
        onClick={() => navigate('/floor')}
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground text-sm"
      >
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> {t('floor_map')}
      </button>
      <PageHeading
        title={`${t('order_ticket')} #${ticket.id}`}
        subtitle={`${t(ticket.order_type || 'dine_in')} · ${t('status')}: ${t('ticket_status_' + (ticket.status || 'open'))}`}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <ClipboardList className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4 me-2" /> {t('add_item')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setTransferOpen(true)}
            className="border-input text-foreground/90 hover:bg-muted"
          >
            <ArrowLeftRight className="h-4 w-4 me-2" /> {t('transfer')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setMergeOpen(true)}
            className="border-input text-foreground/90 hover:bg-muted"
          >
            <Merge className="h-4 w-4 me-2" /> {t('merge')}
          </Button>
        </div>
      </PageHeading>

      {/* Print routing driven by order_type (F-058) */}
      {routing && routing.targets.length > 0 && (
        <Card className="bg-card border-border">
          <CardContent className="p-4 flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-muted-foreground text-sm">
              <Printer className="h-4 w-4" /> {t('print_routing')}:
            </span>
            {routing.targets.map((target) => (
              <Badge key={target} className="bg-muted text-foreground">
                {t('print_target_' + target)}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Line items grouped by course */}
      {items.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <ClipboardList className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('no_ticket_items')}</h3>
            <p className="text-muted-foreground text-sm">{t('no_ticket_items_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {COURSES.filter((c) => items.some((i) => (i.course || 'mains') === c)).map((course) => {
            const courseItems = items.filter((i) => (i.course || 'mains') === course);
            const hasOpen = courseItems.some((i) => (i.fire_state || 'open') === 'open');
            return (
              <Card key={course} className="bg-card border-border">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-foreground font-semibold capitalize">{t('course_' + course)}</h3>
                    {hasOpen && (
                      <Button
                        size="sm"
                        variant="warning"
                        onClick={() => handleFire(course)}
                      >
                        <Flame className="h-4 w-4 me-1" /> {t('fire_course')}
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {courseItems.map((item) => {
                      const fs = item.fire_state || 'open';
                      return (
                        <div
                          key={item.id}
                          className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-foreground text-sm">
                                {item.qty} × {item.name || `#${item.product_id}`}
                              </span>
                              <Badge className={FIRE_BADGE[fs] || FIRE_BADGE.open}>
                                {t('fire_state_' + fs)}
                              </Badge>
                              {item.seat_no != null && (
                                <span className="text-xs text-muted-foreground">
                                  {t('seat')} {item.seat_no}
                                </span>
                              )}
                            </div>
                            {modifierLabel(item.modifiers) && (
                              <p className="text-xs text-brand-600 mt-0.5">+ {modifierLabel(item.modifiers)}</p>
                            )}
                            {item.notes && <p className="text-xs text-muted-foreground mt-0.5">{item.notes}</p>}
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-foreground/90 text-sm tabular-nums">{formatMoney(item.line_total, language)}</span>
                            {fs === 'open' && (
                              <button
                                onClick={() => handleVoid(item)}
                                className="text-muted-foreground hover:text-danger"
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
      <Card className="bg-card border-border">
        <CardContent className="p-4 space-y-2">
          {check ? (
            <div className="space-y-1.5 text-sm">
              <div className="flex items-center justify-between text-foreground/90">
                <span>{t('subtotal')}</span>
                <span className="tabular-nums">{formatMoney(check.subtotal, language)}</span>
              </div>
              <div className="flex items-center justify-between text-foreground/90">
                <span>{t('vat')}</span>
                <span className="tabular-nums">{formatMoney(check.vat_amount, language)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-border pt-1.5 text-foreground">
                <span>{t('total')}</span>
                <span className="tabular-nums">{formatMoney(check.total_amount, language)}</span>
              </div>
              {/* The service charge is its own line, OUTSIDE the VAT base. */}
              <div className="flex items-center justify-between text-foreground/90">
                <span className="flex items-center gap-1">
                  {t('service_charge')}
                  {check.service_charge.pct > 0 && (
                    <span className="text-xs text-muted-foreground">({check.service_charge.pct}%)</span>
                  )}
                  <Badge className="bg-muted text-muted-foreground text-[10px]">{t('outside_vat')}</Badge>
                </span>
                <span className="tabular-nums">{formatMoney(check.service_charge.amount, language)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-border pt-1.5 text-foreground font-semibold">
                <span>{t('amount_due')}</span>
                <span className="tabular-nums">{formatMoney(check.amount_due, language)}</span>
              </div>
            </div>
          ) : (
            <div className="text-foreground font-semibold">
              {t('total')}: <span className="tabular-nums">{formatMoney(grandTotal, language)}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Settled invoice banner (F-059) — replaces the old browser-only flip */}
      {settled && (
        <Card className="bg-success/10 border-success/40">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 text-success shrink-0" />
            <div className="text-sm">
              <p className="text-success font-semibold">
                {settled.fully_settled === false ? t('partial_settled_ok') : t('settled_ok')}
              </p>
              <p className="text-muted-foreground">
                {t('invoice_no')}: {settled.invoice_number} ·{' '}
                {t('amount_due')}: <span className="tabular-nums">{formatMoney(settled.amount_due, language)}</span>
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {settleError && (
        <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-4 py-2 text-danger text-sm">
          <AlertTriangle className="h-4 w-4" />
          <span>{settleError}</span>
        </div>
      )}

      {/* Check + settle (F-059) */}
      {(ticket.status || 'open') !== 'settled' && (ticket.status || 'open') !== 'void' && (
        <Card className="bg-card border-border">
          <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrintCheck}
              className="border-input text-foreground/90 hover:bg-muted"
            >
              <Receipt className="h-4 w-4 me-1" /> {t('print_check')}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setSettleError(null);
                setSettleTip(0);
                setSettleScope('full');
                setSettleSeat(undefined);
                setSettleItemIds(new Set());
                setSettleOpen(true);
              }}
              disabled={items.length === 0}
              variant="success"
            >
              <CheckCircle2 className="h-4 w-4 me-1" /> {t('settle')}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Split + service charge actions */}
      <Card className="bg-card border-border">
        <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setScOpen(true)}
            className="border-input text-foreground/90 hover:bg-muted"
          >
            <Percent className="h-4 w-4 me-1" /> {t('service_charge')}
          </Button>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('seat')}
              className="border-input text-foreground/90 hover:bg-muted"
            >
              <SplitSquareHorizontal className="h-4 w-4 me-1" /> {t('split_by_seat')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('amount')}
              className="border-input text-foreground/90 hover:bg-muted"
            >
              {t('split_by_amount')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSplit('item')}
              className="border-input text-foreground/90 hover:bg-muted"
            >
              {t('split_by_item')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Add-item dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('add_item')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('product')}</label>
              <Select
                value={addForm.product_id != null ? String(addForm.product_id) : 'none'}
                onValueChange={(v) => handleSelectProduct(v === 'none' ? undefined : parseInt(v))}
              >
                <SelectTrigger className="w-full bg-muted border-input text-foreground">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {products.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name} ({p.price})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Combo selector (F-056) — a bundle prices the line at its bundle price */}
            {combos.length > 0 && (
              <div>
                <label className="text-sm text-muted-foreground mb-1 block">{t('combo')}</label>
                <Select
                  value={addForm.combo_id != null ? String(addForm.combo_id) : 'none'}
                  onValueChange={(v) => handleSelectCombo(v === 'none' ? undefined : parseInt(v))}
                >
                  <SelectTrigger className="w-full bg-muted border-input text-foreground">
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">—</SelectItem>
                    {combos.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.name} ({c.bundle_price})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Modifier picker (F-056) — required groups must be satisfied */}
            {productGroups.map((g) => {
              const groupSelected = g.modifiers.filter((m) => selectedMods.has(m.id)).length;
              const unmet = g.required && groupSelected === 0;
              return (
                <div key={g.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm text-foreground">{g.name}</span>
                    {g.required && (
                      <Badge className={unmet ? 'pill-danger' : 'pill-success'}>
                        {t('required')}
                      </Badge>
                    )}
                    {g.max_select != null && g.max_select > 1 && (
                      <span className="text-xs text-muted-foreground">{t('max')} {g.max_select}</span>
                    )}
                  </div>
                  {g.modifiers.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{t('no_modifiers')}</p>
                  ) : (
                    <div className="space-y-1">
                      {g.modifiers.map((m) => (
                        <label
                          key={m.id}
                          className="flex items-center justify-between gap-2 text-sm text-foreground/90 cursor-pointer"
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
                            <span className="text-xs text-muted-foreground">
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
                <label className="text-sm text-muted-foreground mb-1 block">{t('quantity')}</label>
                <Input
                  type="number"
                  value={addForm.qty}
                  onChange={(e) => setAddForm((f) => ({ ...f, qty: parseFloat(e.target.value) || 1 }))}
                  className="bg-muted border-input text-foreground"
                />
              </div>
              <div>
                <label className="text-sm text-muted-foreground mb-1 block">{t('seat')}</label>
                <Input
                  type="number"
                  value={addForm.seat_no ?? ''}
                  onChange={(e) =>
                    setAddForm((f) => ({ ...f, seat_no: e.target.value ? parseInt(e.target.value) : undefined }))
                  }
                  className="bg-muted border-input text-foreground"
                />
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('course')}</label>
              <Select
                value={addForm.course}
                onValueChange={(v) => setAddForm((f) => ({ ...f, course: v }))}
              >
                <SelectTrigger className="w-full bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('course')} />
                </SelectTrigger>
                <SelectContent>
                  {COURSES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {t('course_' + c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('note')}</label>
              <Input
                value={addForm.notes}
                onChange={(e) => setAddForm((f) => ({ ...f, notes: e.target.value }))}
                className="bg-muted border-input text-foreground"
              />
            </div>
            <Button
              onClick={handleAdd}
              disabled={submitting || !canAdd}
              className="w-full"
            >
              {submitting ? t('loading') : t('add_item')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Transfer dialog */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('transfer_ticket')}</DialogTitle>
          </DialogHeader>
          {freeTables.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('no_free_tables')}</p>
          ) : (
            <div className="space-y-2">
              {freeTables.map((tb) => (
                <Button
                  key={tb.id}
                  variant="outline"
                  disabled={submitting}
                  onClick={() => handleTransfer(tb.id)}
                  className="w-full justify-start border-input text-foreground/90 hover:bg-muted"
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
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('merge_ticket')}</DialogTitle>
          </DialogHeader>
          {otherTickets.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('no_other_tickets')}</p>
          ) : (
            <div className="space-y-2">
              {otherTickets.map((o) => (
                <Button
                  key={o.id}
                  variant="outline"
                  disabled={submitting}
                  onClick={() => handleMerge(o.id)}
                  className="w-full justify-start border-input text-foreground/90 hover:bg-muted"
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
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('service_charge')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">{t('service_charge_desc')}</p>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('service_charge_pct')}</label>
              <Input
                type="number"
                min={0}
                value={scPct}
                onChange={(e) => setScPct(parseFloat(e.target.value) || 0)}
                className="bg-muted border-input text-foreground"
              />
            </div>
            <Button
              onClick={handleSetServiceCharge}
              disabled={submitting}
              className="w-full"
            >
              {submitting ? t('loading') : t('apply')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Settle dialog (F-059) — mint a real ZATCA invoice via the sale core */}
      <Dialog open={settleOpen} onOpenChange={setSettleOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('settle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">{t('settle_desc')}</p>

            {/* Settle scope (ISSUE-070): the whole remainder, one seat, or chosen lines */}
            <div>
              <label htmlFor="settle-scope" className="text-sm text-muted-foreground mb-1 block">
                {t('settle_scope')}
              </label>
              <Select
                value={settleScope}
                onValueChange={(v) => {
                  setSettleScope(v as 'full' | 'seat' | 'item');
                  setSettleSeat(undefined);
                  setSettleItemIds(new Set());
                  setSettleTip(0);
                }}
              >
                <SelectTrigger
                  id="settle-scope"
                  aria-label={t('settle_scope')}
                  className="w-full bg-muted border-input text-foreground"
                >
                  <SelectValue placeholder={t('settle_scope')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full">{t('scope_full')}</SelectItem>
                  {seatNumbers.length > 0 && <SelectItem value="seat">{t('scope_seat')}</SelectItem>}
                  <SelectItem value="item">{t('scope_item')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* By seat — pick which seat's lines to bill */}
            {settleScope === 'seat' && (
              <div>
                <label htmlFor="settle-seat" className="text-sm text-muted-foreground mb-1 block">
                  {t('choose_seat')}
                </label>
                <Select
                  value={settleSeat != null ? String(settleSeat) : 'none'}
                  onValueChange={(v) => setSettleSeat(v === 'none' ? undefined : parseInt(v))}
                >
                  <SelectTrigger
                    id="settle-seat"
                    aria-label={t('choose_seat')}
                    className="w-full bg-muted border-input text-foreground"
                  >
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">—</SelectItem>
                    {seatNumbers.map((s) => (
                      <SelectItem key={s} value={String(s)}>
                        {t('seat')} {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* By item — tick the exact lines to bill */}
            {settleScope === 'item' && (
              <div className="space-y-1.5">
                <span className="text-sm text-muted-foreground block">{t('choose_items')}</span>
                {items.map((item) => (
                  <label
                    key={item.id}
                    className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-3 py-2 text-sm text-foreground/90 cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        aria-label={`${item.qty} × ${item.name || `#${item.product_id}`}`}
                        checked={settleItemIds.has(item.id)}
                        onChange={() =>
                          setSettleItemIds((prev) => {
                            const next = new Set(prev);
                            if (next.has(item.id)) next.delete(item.id);
                            else next.add(item.id);
                            return next;
                          })
                        }
                      />
                      {item.qty} × {item.name || `#${item.product_id}`}
                      {item.seat_no != null && (
                        <span className="text-xs text-muted-foreground">
                          ({t('seat')} {item.seat_no})
                        </span>
                      )}
                    </span>
                    <span className="text-muted-foreground tabular-nums">{formatMoney(item.line_total || 0, language)}</span>
                  </label>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between text-foreground font-semibold">
              <span>{t('amount_due')}</span>
              <span className="tabular-nums">{formatMoney(settleBase, language)}</span>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('payment_method')}</label>
              <Select value={settleMethod} onValueChange={(v) => setSettleMethod(v)}>
                <SelectTrigger className="w-full bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('payment_method')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">{t('pay_cash')}</SelectItem>
                  <SelectItem value="card">{t('pay_card')}</SelectItem>
                  <SelectItem value="mada">Mada</SelectItem>
                  <SelectItem value="applepay">Apple Pay</SelectItem>
                  <SelectItem value="stcpay">STC Pay</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label htmlFor="settle-tip" className="text-sm text-muted-foreground mb-1 block">
                {t('tip')}
              </label>
              <Input
                id="settle-tip"
                type="number"
                min={0}
                step="0.01"
                value={settleTip || ''}
                onChange={(e) => setSettleTip(Math.max(0, Number(e.target.value) || 0))}
                className="bg-muted border-input text-foreground"
              />
              <div className="flex gap-2 mt-2">
                {[10, 15, 20].map((pct) => {
                  const base = settleBase;
                  return (
                    <Button
                      key={pct}
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setSettleTip(Number(((base * pct) / 100).toFixed(2)))}
                      className="border-input text-foreground/90 hover:bg-muted"
                    >
                      {pct}%
                    </Button>
                  );
                })}
              </div>
            </div>
            {settleTip > 0 && (
              <div className="flex items-center justify-between text-foreground font-semibold">
                <span>{t('total_with_tip')}</span>
                <span className="tabular-nums">{formatMoney(settleBase + settleTip, language)}</span>
              </div>
            )}
            <Button
              onClick={handleSettle}
              variant="success"
              disabled={submitting || !canSettle}
              className="w-full"
            >
              {submitting ? t('loading') : t('settle')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Split result dialog */}
      <Dialog open={!!split} onOpenChange={(o) => !o && setSplit(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {t('split_bill')} — {split ? t('split_by_' + split.strategy) : ''}
            </DialogTitle>
          </DialogHeader>
          {split && (
            <div className="space-y-2">
              {split.shares.map((s, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm"
                >
                  <span className="text-foreground/90">
                    {s.seat != null
                      ? `${t('seat')} ${s.seat}`
                      : s.name != null
                        ? s.name
                        : `${t('share')} ${s.share}`}
                  </span>
                  <span className="text-foreground tabular-nums">{formatMoney(s.subtotal, language)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-border pt-2 text-sm font-semibold">
                <span className="text-foreground/90">{t('total')}</span>
                <span className="text-foreground tabular-nums">{formatMoney(split.total, language)}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
