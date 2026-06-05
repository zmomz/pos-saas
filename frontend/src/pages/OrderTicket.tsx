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
  type OrderTicket as OrderTicketT,
  type TicketItem,
  type RestaurantTable,
  type SplitResult,
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

export default function OrderTicket() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const { ticketId: ticketIdParam } = useParams<{ ticketId: string }>();
  const ticketId = Number(ticketIdParam);

  const [ticket, setTicket] = useState<OrderTicketT | null>(null);
  const [items, setItems] = useState<TicketItem[]>([]);
  const [products, setProducts] = useState<ProductLite[]>([]);
  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [otherTickets, setOtherTickets] = useState<OrderTicketT[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [submitting, setSubmitting] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState<{
    product_id?: number;
    qty: number;
    course: string;
    seat_no?: number;
    notes: string;
  }>({ qty: 1, course: 'mains', notes: '' });

  const [transferOpen, setTransferOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [split, setSplit] = useState<SplitResult | null>(null);

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
      const [tk, it, prods, tbls, tks] = await Promise.all([
        getOrderTicket(ticketId),
        getTicketItems(ticketId),
        getProducts(),
        getRestaurantTables(),
        getOrderTickets({ status: 'open' }),
      ]);
      setTicket(tk);
      setItems(Array.isArray(it?.items) ? it.items : []);
      setProducts(Array.isArray(prods) ? (prods as ProductLite[]) : []);
      setTables(Array.isArray(tbls?.items) ? tbls.items : []);
      setOtherTickets((Array.isArray(tks?.items) ? tks.items : []).filter((o) => o.id !== ticketId));
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

  async function handleAdd() {
    if (!addForm.product_id) return;
    setSubmitting(true);
    try {
      await addTicketItem(ticketId, {
        product_id: addForm.product_id,
        qty: addForm.qty || 1,
        course: addForm.course,
        seat_no: addForm.seat_no,
        notes: addForm.notes || undefined,
      });
      setAddOpen(false);
      setAddForm({ qty: 1, course: 'mains', notes: '' });
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
            <Button onClick={load} className="bg-blue-600 hover:bg-blue-700 text-white">
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
            <ClipboardList className="h-6 w-6 text-blue-400" />
            {t('order_ticket')} #{ticket.id}
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            {t(ticket.order_type || 'dine_in')} · {t('status')}: {t('ticket_status_' + (ticket.status || 'open'))}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setAddOpen(true)} className="bg-blue-600 hover:bg-blue-700 text-white">
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

      {/* Total + split */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="text-white font-semibold">
            {t('total')}: {grandTotal.toFixed(2)}
          </div>
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
                onChange={(e) =>
                  setAddForm((f) => ({ ...f, product_id: e.target.value ? parseInt(e.target.value) : undefined }))
                }
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
              disabled={submitting || !addForm.product_id}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white"
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
