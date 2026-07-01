import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { SegButton } from '@/components/ui/seg-button';
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
  updateFloorZone,
  deleteFloorZone,
  getRestaurantTables,
  createRestaurantTable,
  openTableOrder,
  createOrderTicket,
  type FloorZone,
  type RestaurantTable,
} from '@/lib/api';
import { toast } from 'sonner';
import { useLanguage } from '@/lib/i18n';
import LoadingState from '@/components/states/LoadingState';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { UtensilsCrossed, Plus, Users, AlertTriangle, Lock, ShoppingBag, Pencil, Trash2 } from 'lucide-react';

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
  const [manageZonesOpen, setManageZonesOpen] = useState(false);
  // Pending rename text keyed by zone id (parity #7).
  const [zoneEdits, setZoneEdits] = useState<Record<number, string>>({});
  const [savingZoneId, setSavingZoneId] = useState<number | null>(null);
  const [zoneToDelete, setZoneToDelete] = useState<FloorZone | null>(null);
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
      toast.error(t('action_failed'));
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
      toast.error(t('action_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  function openManageZones() {
    // Seed each row's editable name from the current zones.
    setZoneEdits(Object.fromEntries(zones.map((z) => [z.id, z.name])));
    setManageZonesOpen(true);
  }

  async function handleRenameZone(zone: FloorZone) {
    const name = (zoneEdits[zone.id] ?? '').trim();
    if (!name || name === zone.name) return;
    setSavingZoneId(zone.id);
    try {
      await updateFloorZone(zone.id, { name });
      toast.success(t('zone_updated'));
      await load();
    } catch (err) {
      console.error('Failed to rename zone:', err);
      toast.error(t('action_failed'));
    } finally {
      setSavingZoneId(null);
    }
  }

  async function handleDeleteZone() {
    if (!zoneToDelete) return;
    setSavingZoneId(zoneToDelete.id);
    try {
      await deleteFloorZone(zoneToDelete.id);
      toast.success(t('zone_deleted'));
      // Drop back to "all" if we were viewing the zone we just removed.
      if (activeZone === zoneToDelete.id) setActiveZone('all');
      setZoneToDelete(null);
      await load();
    } catch (err) {
      console.error('Failed to delete zone:', err);
      toast.error(t('action_failed'));
    } finally {
      setSavingZoneId(null);
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
      toast.error(t('action_failed'));
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
      toast.error(t('action_failed'));
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
  if (loading) return <LoadingState message={t('loading')} />;

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
            <ShoppingBag className="h-4 w-4 me-2" /> {t('new_order')}
          </Button>
          <Dialog open={addZoneOpen} onOpenChange={setAddZoneOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="border-input text-foreground/90 hover:bg-muted">
                <Plus className="h-4 w-4 me-2" /> {t('add_zone')}
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
                <Plus className="h-4 w-4 me-2" /> {t('add_table')}
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
                    <Select
                      value={tableForm.zone_id != null ? String(tableForm.zone_id) : 'none'}
                      onValueChange={(v) =>
                        setTableForm((f) => ({
                          ...f,
                          zone_id: v === 'none' ? undefined : parseInt(v),
                        }))
                      }
                    >
                      <SelectTrigger className="w-full bg-muted border border-input text-foreground rounded-md p-2">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">—</SelectItem>
                        {zones.map((z) => (
                          <SelectItem key={z.id} value={String(z.id)}>
                            {z.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
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
        <div className="flex items-center gap-2">
          <div className="dxr-seg">
            <SegButton
              onClick={() => setActiveZone('all')}
              active={activeZone === 'all'}
            >
              {t('all_zones')}
            </SegButton>
            {zones.map((z) => (
              <SegButton
                key={z.id}
                onClick={() => setActiveZone(z.id)}
                active={activeZone === z.id}
              >
                {z.name}
              </SegButton>
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={openManageZones}
            aria-label={t('manage_zones')}
            title={t('manage_zones')}
            className="text-muted-foreground hover:text-foreground"
          >
            <Pencil className="h-4 w-4" />
          </Button>
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
                className={`min-h-[96px] rounded-lg border p-4 text-start transition-colors ${STATE_STYLES[state] || STATE_STYLES.free}`}
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
              <Select
                value={orderForm.order_type}
                onValueChange={(v) => setOrderForm((f) => ({ ...f, order_type: v }))}
              >
                <SelectTrigger className="w-full bg-muted border border-input text-foreground rounded-md p-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ORDER_TYPES.map((ot) => (
                    <SelectItem key={ot} value={ot}>
                      {t(ot)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
              <Select
                value={newOrderForm.order_type}
                onValueChange={(v) => setNewOrderForm((f) => ({ ...f, order_type: v }))}
              >
                <SelectTrigger className="w-full bg-muted border border-input text-foreground rounded-md p-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TABLELESS_ORDER_TYPES.map((ot) => (
                    <SelectItem key={ot} value={ot}>
                      {t(ot)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

      {/* Manage zones — rename / delete (parity #7) */}
      <Dialog open={manageZonesOpen} onOpenChange={setManageZonesOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('manage_zones')}</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">{t('manage_zones_desc')}</p>
          <div className="mt-2 space-y-3">
            {zones.map((z) => {
              const draft = zoneEdits[z.id] ?? '';
              const dirty = draft.trim() !== '' && draft.trim() !== z.name;
              return (
                <div key={z.id} className="flex items-center gap-2">
                  <Input
                    value={draft}
                    onChange={(e) => setZoneEdits((m) => ({ ...m, [z.id]: e.target.value }))}
                    className="bg-muted border-input text-foreground"
                  />
                  <Button
                    variant="outline"
                    onClick={() => handleRenameZone(z)}
                    disabled={!dirty || savingZoneId === z.id}
                    className="border-input text-foreground/90 hover:bg-muted shrink-0"
                  >
                    {savingZoneId === z.id ? t('loading') : t('save')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setZoneToDelete(z)}
                    aria-label={t('delete_zone')}
                    title={t('delete_zone')}
                    className="text-danger hover:bg-danger/10 shrink-0"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete-zone confirmation (parity #7) */}
      <Dialog open={!!zoneToDelete} onOpenChange={(o) => !o && setZoneToDelete(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('confirm_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {t('delete_zone_confirm_prefix')} <strong>{zoneToDelete?.name}</strong>? {t('action_cannot_be_undone')}
          </p>
          {zoneToDelete && tables.some((tb) => tb.zone_id === zoneToDelete.id) && (
            <p className="text-warning text-sm">{t('delete_zone_tables_warn')}</p>
          )}
          <div className="flex gap-3 pt-2">
            <Button variant="outline" onClick={() => setZoneToDelete(null)} className="flex-1">
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteZone}
              disabled={savingZoneId === zoneToDelete?.id}
              className="flex-1"
            >
              {savingZoneId === zoneToDelete?.id ? t('loading') : t('delete_zone')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
