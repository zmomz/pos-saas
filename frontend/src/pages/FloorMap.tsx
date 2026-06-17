import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  getFloorZones,
  createFloorZone,
  getRestaurantTables,
  createRestaurantTable,
  openTableOrder,
  createOrderTicket,
  type FloorZone,
  type RestaurantTable,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { UtensilsCrossed, Plus, Users, AlertTriangle, Lock, ShoppingBag } from 'lucide-react';

// free | occupied | bill_printed — tile colours mirror the state machine.
const STATE_STYLES: Record<string, string> = {
  free: 'border-success/40 bg-success/10 hover:bg-success/20',
  occupied: 'border-warning/40 bg-warning/10 hover:bg-warning/20',
  bill_printed: 'border-brand-600/40 bg-brand-500/10 hover:bg-brand-500/20',
};

const STATE_BADGE: Record<string, string> = {
  free: 'pill-success',
  occupied: 'pill-warning',
  bill_printed: 'bg-brand-500/20 text-brand-600',
};

const ORDER_TYPES = ['dine_in', 'takeaway', 'delivery'];
// Tableless order types (F-058) — started without selecting a floor table.
const TABLELESS_ORDER_TYPES = ['takeaway', 'delivery'];

export default function FloorMap() {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [zones, setZones] = useState<FloorZone[]>([]);
  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [activeZone, setActiveZone] = useState<number | 'all'>('all');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);

  const [addTableOpen, setAddTableOpen] = useState(false);
  const [addZoneOpen, setAddZoneOpen] = useState(false);
  const [orderTable, setOrderTable] = useState<RestaurantTable | null>(null);
  const [newOrderOpen, setNewOrderOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [tableForm, setTableForm] = useState<{ name: string; seats: number; zone_id?: number }>({
    name: '',
    seats: 4,
  });
  const [zoneForm, setZoneForm] = useState<{ name: string }>({ name: '' });
  const [orderForm, setOrderForm] = useState<{ order_type: string; party_size?: number; customer_name: string }>({
    order_type: 'dine_in',
    customer_name: '',
  });
  // Tableless takeaway/delivery new-order form (F-058).
  const [newOrderForm, setNewOrderForm] = useState<{ order_type: string; customer_name: string; notes: string }>({
    order_type: 'takeaway',
    customer_name: '',
    notes: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [z, tb] = await Promise.all([getFloorZones(), getRestaurantTables()]);
      setZones(Array.isArray(z) ? z : []);
      setTables(Array.isArray(tb?.items) ? tb.items : []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        // Restaurant mode not enabled / wrong business_type → in-page permission state.
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no tables" (UX-02).
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAddTable() {
    setSubmitting(true);
    try {
      await createRestaurantTable({
        name: tableForm.name,
        seats: tableForm.seats || undefined,
        zone_id: tableForm.zone_id,
      });
      setAddTableOpen(false);
      setTableForm({ name: '', seats: 4 });
      await load();
    } catch (err) {
      console.error('Failed to create table:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddZone() {
    setSubmitting(true);
    try {
      await createFloorZone({ name: zoneForm.name });
      setAddZoneOpen(false);
      setZoneForm({ name: '' });
      await load();
    } catch (err) {
      console.error('Failed to create zone:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOpenOrder() {
    if (!orderTable) return;
    setSubmitting(true);
    try {
      await openTableOrder(orderTable.id, {
        order_type: orderForm.order_type,
        party_size: orderForm.party_size,
        customer_name: orderForm.customer_name || undefined,
      });
      setOrderTable(null);
      setOrderForm({ order_type: 'dine_in', customer_name: '' });
      await load();
    } catch (err) {
      console.error('Failed to open order:', err);
    } finally {
      setSubmitting(false);
    }
  }

  // Start a tableless takeaway/delivery order and jump straight to its ticket (F-058).
  async function handleNewOrder() {
    setSubmitting(true);
    try {
      const ticket = await createOrderTicket({
        order_type: newOrderForm.order_type,
        customer_name: newOrderForm.customer_name || undefined,
        notes: newOrderForm.notes || undefined,
      });
      setNewOrderOpen(false);
      setNewOrderForm({ order_type: 'takeaway', customer_name: '', notes: '' });
      navigate(`/floor/ticket/${ticket.id}`);
    } catch (err) {
      console.error('Failed to start order:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTileClick(table: RestaurantTable) {
    if ((table.state || 'free') === 'free') {
      setOrderForm({ order_type: 'dine_in', customer_name: '' });
      setOrderTable(table);
      return;
    }
    // An occupied table with an open ticket opens its order ticket (F-055): add/
    // fire/transfer/merge/split lines, then check → settle (F-059). The ticket is
    // freed by a real settlement (mint a ZATCA invoice), never a browser-only flip.
    if (table.current_ticket_id) {
      navigate(`/floor/ticket/${table.current_ticket_id}`);
    }
  }

  const visibleTables =
    activeZone === 'all' ? tables : tables.filter((tb) => tb.zone_id === activeZone);

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
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-danger mx-auto mb-3" />
            <p className="text-foreground/90 mb-4">{t('floor_load_error')}</p>
            <Button onClick={load}>
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        title={t('floor_map')}
        subtitle={t('floor_map_desc')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <UtensilsCrossed className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setNewOrderOpen(true)}
            className="border-input text-foreground/90 hover:bg-muted"
          >
            <ShoppingBag className="h-4 w-4 mr-2" /> {t('new_order')}
          </Button>
          <Dialog open={addZoneOpen} onOpenChange={setAddZoneOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="border-input text-foreground/90 hover:bg-muted">
                <Plus className="h-4 w-4 mr-2" /> {t('add_zone')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border text-foreground">
              <DialogHeader>
                <DialogTitle className="text-foreground">{t('add_zone')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">{t('zone_name')}</label>
                  <Input
                    value={zoneForm.name}
                    onChange={(e) => setZoneForm({ name: e.target.value })}
                    className="bg-muted border-input text-foreground"
                  />
                </div>
                <Button
                  onClick={handleAddZone}
                  disabled={submitting || !zoneForm.name}
                  className="w-full"
                >
                  {submitting ? t('loading') : t('create_zone')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={addTableOpen} onOpenChange={setAddTableOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" /> {t('add_table')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border text-foreground">
              <DialogHeader>
                <DialogTitle className="text-foreground">{t('add_table')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">{t('table_name')}</label>
                  <Input
                    value={tableForm.name}
                    onChange={(e) => setTableForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="T1"
                    className="bg-muted border-input text-foreground"
                  />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">{t('table_seats')}</label>
                  <Input
                    type="number"
                    value={tableForm.seats}
                    onChange={(e) => setTableForm((f) => ({ ...f, seats: parseInt(e.target.value) || 0 }))}
                    className="bg-muted border-input text-foreground"
                  />
                </div>
                {zones.length > 0 && (
                  <div>
                    <label className="text-sm text-muted-foreground mb-1 block">{t('all_zones')}</label>
                    <select
                      value={tableForm.zone_id ?? ''}
                      onChange={(e) =>
                        setTableForm((f) => ({
                          ...f,
                          zone_id: e.target.value ? parseInt(e.target.value) : undefined,
                        }))
                      }
                      className="w-full bg-muted border border-input text-foreground rounded-md p-2"
                    >
                      <option value="">—</option>
                      {zones.map((z) => (
                        <option key={z.id} value={z.id}>
                          {z.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <Button
                  onClick={handleAddTable}
                  disabled={submitting || !tableForm.name}
                  className="w-full"
                >
                  {submitting ? t('loading') : t('create_table')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </PageHeading>

      {/* Zone tabs */}
      {zones.length > 0 && (
        <div className="dxr-seg">
          <button
            onClick={() => setActiveZone('all')}
            data-active={activeZone === 'all'}
          >
            {t('all_zones')}
          </button>
          {zones.map((z) => (
            <button
              key={z.id}
              onClick={() => setActiveZone(z.id)}
              data-active={activeZone === z.id}
            >
              {z.name}
            </button>
          ))}
        </div>
      )}

      {/* Tables grid / empty state */}
      {visibleTables.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <UtensilsCrossed className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('no_tables')}</h3>
            <p className="text-muted-foreground text-sm">{t('no_tables_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {visibleTables.map((table) => {
            const state = table.state || 'free';
            return (
              <button
                key={table.id}
                onClick={() => handleTileClick(table)}
                className={`rounded-lg border p-4 text-start transition-colors ${STATE_STYLES[state] || STATE_STYLES.free}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-foreground font-semibold">{table.name}</span>
                  <Badge className={STATE_BADGE[state] || STATE_BADGE.free}>
                    {t(state === 'occupied' ? 'tbl_occupied' : state === 'bill_printed' ? 'tbl_bill_printed' : 'tbl_free')}
                  </Badge>
                </div>
                <div className="flex items-center gap-1 text-muted-foreground text-xs">
                  <Users className="h-3 w-3" />
                  <span>{table.seats ?? 0}</span>
                </div>
                {state === 'free' && (
                  <span className="mt-2 inline-block text-xs text-success">{t('open_order')}</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Open-order dialog */}
      <Dialog open={!!orderTable} onOpenChange={(o) => !o && setOrderTable(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {t('open_order')} — {orderTable?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('order_type')}</label>
              <select
                value={orderForm.order_type}
                onChange={(e) => setOrderForm((f) => ({ ...f, order_type: e.target.value }))}
                className="w-full bg-muted border border-input text-foreground rounded-md p-2"
              >
                {ORDER_TYPES.map((ot) => (
                  <option key={ot} value={ot}>
                    {t(ot)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('party_size')}</label>
              <Input
                type="number"
                value={orderForm.party_size ?? ''}
                onChange={(e) =>
                  setOrderForm((f) => ({
                    ...f,
                    party_size: e.target.value ? parseInt(e.target.value) : undefined,
                  }))
                }
                className="bg-muted border-input text-foreground"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('customer_name')}</label>
              <Input
                value={orderForm.customer_name}
                onChange={(e) => setOrderForm((f) => ({ ...f, customer_name: e.target.value }))}
                className="bg-muted border-input text-foreground"
              />
            </div>
            <Button
              onClick={handleOpenOrder}
              disabled={submitting}
              className="w-full"
            >
              {submitting ? t('loading') : t('open_order')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Tableless new-order dialog (F-058) — takeaway / delivery skip table selection */}
      <Dialog open={newOrderOpen} onOpenChange={setNewOrderOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('new_order')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-muted-foreground text-sm">{t('new_order_desc')}</p>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('order_type')}</label>
              <select
                value={newOrderForm.order_type}
                onChange={(e) => setNewOrderForm((f) => ({ ...f, order_type: e.target.value }))}
                className="w-full bg-muted border border-input text-foreground rounded-md p-2"
              >
                {TABLELESS_ORDER_TYPES.map((ot) => (
                  <option key={ot} value={ot}>
                    {t(ot)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('customer_name')}</label>
              <Input
                value={newOrderForm.customer_name}
                onChange={(e) => setNewOrderForm((f) => ({ ...f, customer_name: e.target.value }))}
                className="bg-muted border-input text-foreground"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('note')}</label>
              <Input
                value={newOrderForm.notes}
                onChange={(e) => setNewOrderForm((f) => ({ ...f, notes: e.target.value }))}
                className="bg-muted border-input text-foreground"
              />
            </div>
            <Button
              onClick={handleNewOrder}
              disabled={submitting}
              className="w-full"
            >
              {submitting ? t('loading') : t('start_order')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
